#ifndef LOBBY_H
#define LOBBY_H

#include "Player.h"
#include <map>
#include <memory>
#include "game/GameRoom.h"
#include "../protocol/Message.h"

class TcpServer;

class Lobby
{
public:
    Lobby(TcpServer &server);

    // Adds a new connection to the lobby
    void addPlayer(int fd);

    // Removes a player (disconnect)
    void removePlayer(int fd);
    // Destroys a player completely
    void destroyPlayer(int fd);
    void handleInvalidMessage(std::shared_ptr<Player> player);

    // Retrieves all players
    std::map<int, std::shared_ptr<Player>> &getAllPlayers() { return players; }

    // checks if a nickname is already taken
    bool nicknameExists(const std::string nickname);

    // Retrieves player object by socket FD
    std::shared_ptr<Player> getPlayer(int fd);

    // Additional lobby management
    void handle(std::shared_ptr<Player> player, const Message &msg);

    bool initGamerooms(int numberOfRooms);

    std::string getLobbyState();

    // Assigns a player to a specific game room
    bool assignPlayerToRoom(std::shared_ptr<Player> player, int roomId);

    void update();

    void broadcastMessage(const std::string &command, const std::string &args);

    void dirtyPlayerState() { playerStateChanged = true; }

private:
    std::map<int, std::shared_ptr<Player>> players;
    std::map<std::string, std::shared_ptr<Player>> disconnectedPlayers;
    std::map<int, GameRoom> rooms;
    TcpServer &server;
    bool playerStateChanged = false;
};

#endif