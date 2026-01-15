#include "Lobby.h"
#include "../core/Logger.h"
#include "../network/TcpServer.h"
#include "../core/Utils.h"

Lobby::Lobby(TcpServer &srv) : server(srv) {}

void Lobby::addPlayer(int fd)
{
    players[fd] = std::make_shared<Player>(fd);
    Logger::debug("Lobby: Player added on FD " + std::to_string(fd));
    server.sendMessage(fd, "REQ_NICK", " ");
}

void Lobby::removePlayer(int fd)
{
    auto it = players.find(fd);
    if (it != players.end())
    {
        if (it->second->getState() == PlayerState::IN_GAMEROOM)
        {
            auto roomIt = rooms.find(it->second->getRoomId());
            if (roomIt != rooms.end())
            {
                roomIt->second.removePlayer(it->second);
                roomIt->second.broadcastMessage("ROMSTAUP", roomIt->second.getRoomState());
            }
        }
        players.erase(it);
        dirtyPlayerState();
        Logger::debug("Lobby: Player removed on FD " + std::to_string(fd));
    }
}

std::shared_ptr<Player> Lobby::getPlayer(int fd)
{
    auto it = players.find(fd);
    if (it != players.end())
    {
        return it->second;
    }
    return nullptr;
}

void Lobby::update()
{

    if (playerStateChanged)
    {
        auto lobbyState = getLobbyState();
        broadcastMessage("LBBYINFO", lobbyState);
        playerStateChanged = false;
    }

    // Get new players lobby information
    for (auto &pair : players)
    {
        auto player = pair.second;
        // Here you can add code to update player state in the lobby if needed
        if (player->getNickname().empty())
        {
            // server.sendMessage(player->getFd(), "REQ_NICK", " ");
        }
    }
}

void Lobby::broadcastMessage(const std::string &command, const std::string &args)
{
    for (const auto &pair : players)
    {
        if (pair.second->getNickname().empty())
            continue; // Skip players without a nickname (not fully logged in)
        if (pair.second->getState() != PlayerState::LOBBY)
            continue; // Skip players not in the lobby
        server.sendMessage(pair.second->getFd(), command, args);
    }
}

std::string Lobby::getLobbyState()
{
    std::string state = "";
    state += "ONLINE;" + std::to_string(players.size()) + ":";
    state += "ROOMS;" + std::to_string(rooms.size()) + ":";
    for (const auto &roomPair : rooms)
    {
        state += "R" + std::to_string(roomPair.first) + ";" +
                 std::to_string(roomPair.second.getPlayerCount()) + "/" + std::to_string(MAX_PLAYERS) + ";" + std::to_string(static_cast<int>(roomPair.second.getState())) + ":";
    }
    return state;
}

bool Lobby::initGamerooms(int numberOfRooms)
{
    for (int i = 0; i < numberOfRooms; ++i)
    {
        rooms.try_emplace(i, i);
    }
    Logger::info("Lobby: Initialized " + std::to_string(numberOfRooms) + " game rooms");
    return true;
}

void Lobby::handle(std::shared_ptr<Player> player, const Message &msg)
{
    if (player->getNickname().empty() && msg.command != "LOGIN___")
    {
        Logger::error("Lobby: Player FD " + std::to_string(player->getFd()) + " attempted command without login");
        server.sendMessage(player->getFd(), "REQ_NICK", "");
        return;
    }
    if (msg.command == "LVRO____")
    {
        // Player wants to leave the game room
        auto it = rooms.find(player->getRoomId());
        if (it != rooms.end())
        {
            it->second.removePlayer(player);
            server.sendMessage(player->getFd(), "ACK_LVRO", " ");
            if (it->second.getPlayerCount() == 0)
            {
                it->second.ResetDefaultState();
                Logger::info("Lobby: Room " + std::to_string(it->first) + " reset to default state (no players left)");
                dirtyPlayerState();
                return;
            }
            if (it->second.getState() == GameState::WAITING_FOR_PLAYERS) // Only broadcast if in waiting state - avoid mid-game updates/confusion might delete later for reconnects
            {
                it->second.broadcastMessage("ROMSTAUP", it->second.getRoomState());
            }
            playerStateChanged = true;
        }
        else
        {
            Logger::error("Lobby: Player FD " + std::to_string(player->getFd()) + " is in unknown room " + std::to_string(player->getRoomId()));
            server.sendMessage(player->getFd(), "LEAVENCK", "Not in a valid room");
        }
    }
    else if (player->getState() == PlayerState::IN_GAMEROOM)
    {
        // Forward message to the appropriate game room
        auto it = rooms.find(player->getRoomId());
        if (it != rooms.end())
        {
            it->second.handle(player, msg);
        }
        else
        {
            Logger::error("Lobby: Player FD " + std::to_string(player->getFd()) + " is in unknown room " + std::to_string(player->getRoomId()));
        }
    }
    // Handle messages from players in the lobby
    else if (msg.command == "LOGIN___")
    {
        // Login command has no arguments
        if (msg.args.size() < 1)
        {
            Logger::error("Lobby: LOGIN___ command missing arguments");
            server.sendMessage(player->getFd(), "NACK_NIC", "Nickname required");
            return;
        }
        // Check if nickname is already taken
        if (nicknameExists(msg.args[0]))
        {
            Logger::error("Lobby: Player FD " + std::to_string(player->getFd()) + " failed LOGIN___ command - nickname already taken (" + msg.args[0] + ")");
            server.sendMessage(player->getFd(), "NACK_NIC", "Nickname already taken");
            return;
        }
        // check if nickname is valid
        if (Utils::validateNickname(msg.args[0]))
        {
            player->setNickname(msg.args[0]);
            Logger::info("Lobby: Player FD " + std::to_string(player->getFd()) + " set nickname to " + player->getNickname());
            server.sendMessage(player->getFd(), "ACK__NIC", msg.args[0] + ";" + std::to_string(player->getCredits()));
            playerStateChanged = true;
        }
        else
        {
            server.sendMessage(player->getFd(), "NACK_NIC", "Invalid nickname");
            Logger::error("Lobby: LOGIN___ command missing arguments or invalid nickname" + (msg.args[0].empty() ? "" : " (" + msg.args[0] + ")"));
        }
    }
    else if (msg.command == "JOIN____")
    {
        // Handle player joining a game room
        if (msg.args.size() == 1)
        {
            int roomId = std::stoi(msg.args[0]);
            if (assignPlayerToRoom(player, roomId))
            {
                server.sendMessage(player->getFd(), "ACK__JON", " ");
                auto it = rooms.find(roomId);
                it->second.broadcastMessage("ROMSTAUP", it->second.getRoomState());
            }
            else
            {
                server.sendMessage(player->getFd(), "NACK_JON", "Cannot join room");
            }
        }
        else
        {
            Logger::error("Lobby: JOIN____ command missing arguments");
            server.sendMessage(player->getFd(), "NACK_JON", "Missing room ID");
        }
    }
    else if (msg.command == "PING____")
    {
        server.sendMessage(player->getFd(), "ACK_PING", " ");
    }
    else
    {
        Logger::error("Lobby: Unknown message command");
    }
}

bool Lobby::assignPlayerToRoom(std::shared_ptr<Player> player, int roomId)
{
    auto it = rooms.find(roomId);
    if (it != rooms.end() && it->second.getPlayerCount() < MAX_PLAYERS && it->second.getState() == GameState::WAITING_FOR_PLAYERS)
    {
        it->second.addPlayer(player);
        player->setRoomId(roomId);
        player->setState(PlayerState::IN_GAMEROOM);
        playerStateChanged = true;
        Logger::info("Lobby: Player FD " + std::to_string(player->getFd()) + " assigned to room " + std::to_string(roomId));
        return true;
    }
    Logger::error("Lobby: Room " + std::to_string(roomId) + " not found");
    return false;
}

bool Lobby::nicknameExists(const std::string nickname)
{
    for (const auto &pair : players)
    {
        if (pair.second->getNickname() == nickname)
        {
            return true;
        }
    }
    return false;
}