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

int parse_arguments(int argc, char *argv[], Config &config)
{
    // Basic argument parsing: ./server -i <ip> -p <port> -r <rooms> -m <maxPlayers>
    for (int i = 1; i < argc; i++)
    {
        if (std::string(argv[i]) == "-i" && i + 1 < argc)
        {
            config.ipAddress = argv[++i];
        }
        else if (std::string(argv[i]) == "-p" && i + 1 < argc)
        {
            try
            {
                config.port = std::stoi(argv[++i]);
            }
            catch (const std::exception &e)
            {
                Logger::error("Invalid port number provided. Using default port " + std::to_string(Config().port));
                return 1;
            }
        }
        else if (std::string(argv[i]) == "-r" && i + 1 < argc)
        {
            try
            {
                config.rooms = std::stoi(argv[++i]);
            }
            catch (const std::exception &e)
            {
                Logger::error("Invalid rooms number provided. Using default rooms " + std::to_string(Config().rooms));
                return 1;
            }
            if (config.rooms < 1 || config.rooms > 20)
            {
                Logger::error("Rooms number out of valid range (1-20). Using default rooms " + std::to_string(Config().rooms));
                config.rooms = Config().rooms;
                return 1;
            }
        }
        else if (std::string(argv[i]) == "-m" && i + 1 < argc)
        {
            try
            {
                config.maxPlayers = std::stoi(argv[++i]);
            }
            catch (const std::exception &e)
            {
                Logger::error("Invalid max players number provided. Using default max players " + std::to_string(Config().maxPlayers));
                return 1;
            }
            if (config.maxPlayers < 1 || config.maxPlayers > 300)
            {
                Logger::error("Max players number out of valid range (1-300). Using default max players " + std::to_string(Config().maxPlayers));
                config.maxPlayers = Config().maxPlayers;
                return 1;
            }
        }
        else if (std::string(argv[i]) == "-h" || std::string(argv[i]) == "--help")
        {
            std::cout << "Usage: " << argv[0] << " [options]\n";
            std::cout << "Options:\n";
            std::cout << "  -i <ip>       IP address to bind to (default: 0.0.0.0)\n";
            std::cout << "  -p <port>     Port number (default: 10000)\n";
            std::cout << "  -r <rooms>    Number of rooms (1-20, default: 6)\n";
            std::cout << "  -m <players>  Max players (1-300, default: 20)\n";
            std::cout << "  -h, --help    Show this help message\n";
            return 2;
        }
        else
        {
            Logger::error("Unknown argument: " + std::string(argv[i]));
            return 1;
        }
    }

    return 0;
}

int main(int argc, char *argv[])
{
    Config config;
    // Basic argument parsing: ./server -i <ip> -p <port> -r <rooms> -m <maxPlayers>
    int parseResult = parse_arguments(argc, argv, config);

    switch (parseResult)
    {
    case 0:
        Logger::info("Arguments parsed successfully.");
        break;
    case 1:
        Logger::error("Error parsing arguments.");
        return 1;
    case 2:
        // Help was shown, exit gracefully
        return 0;
    default:
        break;
    }

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