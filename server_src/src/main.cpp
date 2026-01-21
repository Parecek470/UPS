#include "core/Config.h"
#include "core/Logger.h"
#include "network/TcpServer.h"
#include <iostream>
#include <csignal>

void signalHandler(int signum)
{
    Logger::info("Signal " + std::to_string(signum) + " received. Shutting down.");
    exit(signum);
}

int main(int argc, char *argv[])
{
    Config config;

    // Basic argument parsing: ./server <ip> <port> <rooms> <maxPlayers>
    if (argc > 1)
        config.ipAddress = argv[1];
    if (argc > 2)
        config.port = std::stoi(argv[2]);
    if (argc > 3)
        config.rooms = std::stoi(argv[3]);
    if (argc > 4)
        config.maxPlayers = std::stoi(argv[4]);

    // 1. Handle SIGINT (Ctrl+C) for graceful exit
    signal(SIGINT, signalHandler);

    // 2. Ignore SIGPIPE: Writing to a closed socket should return error, not kill process
    signal(SIGPIPE, SIG_IGN);

    Logger::info("Starting Blackjack Server...");

    try
    {
        TcpServer server(config);
        server.run();
    }
    catch (const std::exception &e)
    {
        Logger::error("Fatal error: " + std::string(e.what()));
        return 1;
    }

    return 0;
}