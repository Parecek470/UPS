/**
 * Server for blackjack
 * Author: Marek Manzel
 * 
 * Config.h - Configuration structure for the blackjack server
 * Contains server configuration parameters including IP address, port, 
 * number of game rooms, and maximum players allowed.
 */

#ifndef CONFIG_H
#define CONFIG_H

#include <string>

struct Config
{
    std::string ipAddress;
    int port;
    int rooms;
    int maxPlayers;

    // Defaults: Port 10000, 6 rooms max, 20 players max connected
    Config() : ipAddress("0.0.0.0"), port(10000), rooms(6), maxPlayers(20) {}
};

#endif