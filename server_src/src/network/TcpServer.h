#ifndef TCP_SERVER_H
#define TCP_SERVER_H

#include "../core/Config.h"
#include "../game/Lobby.h"
#include "ClientConnection.h"
#include <sys/select.h>
#include <map>

class TcpServer
{
public:
    TcpServer(const Config &config);
    ~TcpServer();

    TcpServer(const TcpServer &) = delete;
    TcpServer &operator=(const TcpServer &) = delete;
    TcpServer(TcpServer &&) = delete;
    TcpServer &operator=(TcpServer &&) = delete;

    // Main blocking loop
    void run();
    void sendMessage(int fd, std::string command, std::string args);

    // Game State
    Lobby lobby;

private:
    // Core networking methods
    void initSocket();
    void handleNewConnection();
    void handleClientData(int fd);
    void disconnectClient(int fd);

    Config config;
    int serverSocket;
    bool isRunning;

    // Tracking active connections
    std::map<int, ClientConnection *> connections;

    // Select() file descriptor sets
    fd_set masterSet;
    int maxFd;
};

#endif