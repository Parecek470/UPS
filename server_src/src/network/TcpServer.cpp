#include "TcpServer.h"
#include "../core/Logger.h"
#include "../protocol/Parser.h"
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <fcntl.h>
#include <arpa/inet.h>
#include <cstring>
#include <vector>
#include <chrono>

TcpServer::TcpServer(const Config &cfg)
    : config(cfg), serverSocket(-1), isRunning(false), maxFd(0), lobby(*this)
{
    FD_ZERO(&masterSet);
}

TcpServer::~TcpServer()
{
    if (serverSocket != -1)
        close(serverSocket);
    // Cleanup connections
    for (auto &pair : connections)
    {
        delete pair.second;
    }
}

void TcpServer::initSocket()
{
    serverSocket = socket(AF_INET, SOCK_STREAM, 0);
    if (serverSocket < 0)
    {
        Logger::error("Failed to create socket");
        exit(EXIT_FAILURE);
    }

    // Allow immediate port reuse after restart
    int opt = 1;
    setsockopt(serverSocket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    // Set non-blocking
    int flags = fcntl(serverSocket, F_GETFL, 0);
    fcntl(serverSocket, F_SETFL, flags | O_NONBLOCK);

    sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    if (config.ipAddress == "0.0.0.0")
        addr.sin_addr.s_addr = INADDR_ANY;
    else if (inet_pton(AF_INET, config.ipAddress.c_str(), &addr.sin_addr) <= 0)
    {
        Logger::error("Invalid IP address: " + config.ipAddress);
        exit(EXIT_FAILURE);
    }
    addr.sin_port = htons(config.port);

    if (bind(serverSocket, (struct sockaddr *)&addr, sizeof(addr)) < 0)
    {
        Logger::error("Failed to bind to port " + std::to_string(config.port));
        exit(EXIT_FAILURE);
    }

    if (listen(serverSocket, 10) < 0)
    {
        Logger::error("Failed to listen");
        exit(EXIT_FAILURE);
    }

    FD_SET(serverSocket, &masterSet);
    maxFd = serverSocket;
    Logger::info("Server listening on port " + std::to_string(config.port));

    GameRoom::setServer(this);
    // Initialize game rooms in the lobby
    if (!lobby.initGamerooms(config.rooms))
    {
        Logger::error("Failed to initialize game rooms");
        exit(EXIT_FAILURE);
    }
}

void TcpServer::run()
{
    initSocket();
    isRunning = true;

    auto lastTask = std::chrono::steady_clock::now();

    while (isRunning)
    {
        fd_set readFds = masterSet;
        // 1-second timeout for select to allow periodic cleanup tasks
        struct timeval tv = {1, 0};

        int activity = select(maxFd + 1, &readFds, nullptr, nullptr, &tv);

        if (activity < 0 && errno != EINTR)
        {
            Logger::error("Select error");
            break;
        }

        if (activity > 0)
        {
            // 1. Check for new incoming connections
            if (FD_ISSET(serverSocket, &readFds))
            {
                handleNewConnection();
            }

            // 2. Check data from existing clients
            // Create a list of FDs to check to safely modify map inside loop
            std::vector<int> fdsToCheck;
            for (auto const &[fd, conn] : connections)
            {
                fdsToCheck.push_back(fd);
            }

            for (int fd : fdsToCheck)
            {
                if (FD_ISSET(fd, &readFds))
                {
                    handleClientData(fd);
                }
            }
        }

        lobby.update();
        // -------------------------------------------------------------
        // PERIODIC TASK: Run every 3 Seconds
        // -------------------------------------------------------------

        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - lastTask).count();

        if (elapsed >= 3)
        {
            auto allPlayers = lobby.getAllPlayers();
            for (auto &pair : allPlayers)
            {
                int fd = pair.first;
                auto player = pair.second;

                long inactiveSeconds = player->getSecondsSinceLastActivity();
                if (inactiveSeconds >= 10)
                {
                    Logger::info("Client timed out (No heartbeat): " + std::to_string(fd));
                    disconnectClient(fd);
                }
                else if (inactiveSeconds >= 3)
                {
                    // Send PING to check if client is alive
                    sendMessage(fd, "PING____", "");
                }
            }
        }

        // -------------------------------------------------------------
    }
}

void TcpServer::handleNewConnection()
{
    sockaddr_in clientAddr;
    socklen_t clientLen = sizeof(clientAddr);
    int newFd = accept(serverSocket, (struct sockaddr *)&clientAddr, &clientLen);

    if (newFd < 0)
    {
        if (errno != EWOULDBLOCK)
            Logger::error("Accept failed");
        return;
    }

    if (lobby.getAllPlayers().size() >= static_cast<size_t>(config.maxPlayers))
    {
        Logger::info("Rejected connection: Max players reached");
        sendMessage(newFd, "CON_FAIL", "Max players reached");
        close(newFd);
        return;
    }
    // Set non-blocking
    int flags = fcntl(newFd, F_GETFL, 0);
    fcntl(newFd, F_SETFL, flags | O_NONBLOCK);

    FD_SET(newFd, &masterSet);
    if (newFd > maxFd)
        maxFd = newFd;

    // Create tracking objects
    connections[newFd] = new ClientConnection(newFd);
    Logger::info("New client connected on FD " + std::to_string(newFd));
    lobby.addPlayer(newFd);
}

void TcpServer::sendMessage(int fd, std::string command, std::string args)
{
    // 1. Protocol Requirement: Start with "BJ:"
    std::string finalMessage = "BJ:" + command;

    // Add arguments if they exist (assuming a space separator)
    if (!args.empty())
    {
        finalMessage += ":" + args;
    }

    // 2. Protocol Requirement: Messages must be newline-terminated
    if (finalMessage.back() != '\n')
    {
        finalMessage += '\n';
    }

    // 3. Send data using the standard BSD socket call
    ssize_t bytesSent = send(fd, finalMessage.c_str(), finalMessage.size(), 0);

    if (bytesSent < 0)
    {
        // Handle send errors
        if (errno == EWOULDBLOCK || errno == EAGAIN)
        {
            Logger::error("Socket buffer full for FD " + std::to_string(fd));
        }
        else
        {
            Logger::error("Failed to send to FD " + std::to_string(fd));
        }
    }
    else
    {
        // 4. Log the actual message sent (trimming the newline for cleaner logs is optional but nice)
        // We use finalMessage here to see exactly what went over the wire.
        Logger::debug("Sent to FD " + std::to_string(fd) + ": " + finalMessage);
    }
}

void TcpServer::handleClientData(int fd)
{
    char buf[1024];
    int bytesRead = recv(fd, buf, sizeof(buf), 0);

    if (bytesRead <= 0)
    {
        // 0 = Closed by client, <0 = Error
        disconnectClient(fd);
    }
    else
    {
        // keep player activity updated trough slow trafic
        auto player = lobby.getPlayer(fd);
        if (player)
        {
            player->refreshLastActivity();
        }
        // Append data to buffer
        auto conn = connections[fd];
        if (conn->appendBuffer(buf, bytesRead))
        {
            // If we have complete lines, process them
            auto msgs = conn->getMessages();

            for (const auto &rawMsg : msgs)
            {
                Message msg = Parser::parse(rawMsg);

                if (!msg.valid)
                {
                    Logger::log(LogLevel::WARNING, "Invalid message format from FD" + std::to_string(fd));
                    if (player)
                    {
                        player->incrementInvalidMsg();
                        // Requirement: Disconnect after N invalid messages
                        if (player->getInvalidMsgCount() >= 3)
                        {
                            Logger::info("Kicking client (Too many invalid msgs): " + std::to_string(fd));
                            disconnectClient(fd);
                            return;
                        }
                    }
                }
                else
                {
                    Logger::debug("Recv FD " + std::to_string(fd) + ": " + msg.command);
                    // Route valid messages (e.g., to Lobby or GameRoom) and update last activity for timeout tracking
                    if (player)
                    {
                        if (msg.command == "PING____")
                        {
                            // Handle PING command (keep-alive)
                            sendMessage(fd, "PONG____", "");
                            Logger::debug("Responded to PING from FD " + std::to_string(fd));
                        }
                        else if (msg.command == "PONG____")
                        {
                            player->refreshLastActivity();
                        }
                        else
                        {
                            lobby.handle(player, msg);
                        }
                    }
                }
            }
        }
    }
}

void TcpServer::disconnectClient(int fd)
{
    close(fd);
    FD_CLR(fd, &masterSet);

    if (connections.count(fd))
    {
        delete connections[fd];
        connections.erase(fd);
    }

    lobby.removePlayer(fd);
    Logger::info("Client disconnected FD " + std::to_string(fd));
}