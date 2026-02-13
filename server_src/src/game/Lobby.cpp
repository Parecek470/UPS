#include "Lobby.h"
#include "../core/Logger.h"
#include "../network/TcpServer.h"
#include "../core/Utils.h"

Lobby::Lobby(TcpServer &srv) : server(srv) {}

void Lobby::addPlayer(int fd)
{
    players[fd] = std::make_shared<Player>(fd);
    players[fd]->refreshLastActivity();
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
            if (roomIt != rooms.end() && roomIt->second.getState() != GameState::PLAYING)
            {
                roomIt->second.removePlayer(it->second);
                roomIt->second.broadcastMessage("ROMSTAUP", roomIt->second.getRoomState());
            }
            else
            {
                roomIt->second.broadcastMessage("GAMESTAT", roomIt->second.getGameState());
            }
        }
        if (!it->second->getNickname().empty())
        {
            disconnectedPlayers[it->second->getNickname()] = it->second;
        }
        players.erase(fd);
        dirtyPlayerState();
        Logger::debug("Lobby: Player flagged as disconnected on FD " + std::to_string(fd));
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

    for (auto &room : rooms)
    {
        if (room.second.getState() != GameState::ROUND_END || (room.second.areAllPlayersOffline() && room.second.getState() == GameState::ROUND_END))
            room.second.update();
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
        handleInvalidMessage(player);
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
            if (it->second.getState() == GameState::WAITING_FOR_PLAYERS) // Only broadcast if in waiting state - avoid mid-game updates
            {
                it->second.broadcastMessage("ROMSTAUP", it->second.getRoomState());
            }
            playerStateChanged = true;
        }
        else
        {
            // invalid room
            Logger::error("Lobby: Player FD " + std::to_string(player->getFd()) + " is in unknown room " + std::to_string(player->getRoomId()));
            server.sendMessage(player->getFd(), "NACKLVRO", "Not in a valid room");
            handleInvalidMessage(player);
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
            handleInvalidMessage(player);
            return;
        }
        // Check if nickname is already taken
        if (nicknameExists(msg.args[0]) && msg.args[0] != player->getNickname())
        {
            Logger::error("Lobby: Player FD " + std::to_string(player->getFd()) + " failed LOGIN___ command - nickname already taken (" + msg.args[0] + ")");
            server.sendMessage(player->getFd(), "NACK_NIC", "Nickname already taken");
            return;
        }
        // reconnecting disconnected player
        if (disconnectedPlayers.count(msg.args[0]) > 0)
        {
            auto oldPlayer = disconnectedPlayers[msg.args[0]];

            int newFd = player->getFd();
            oldPlayer->setFd(newFd);
            players[newFd] = oldPlayer;
            disconnectedPlayers.erase(msg.args[0]);
            oldPlayer->refreshLastActivity();
            oldPlayer->resetInvalidMsgCount();
            server.sendMessage(newFd, "ACK__REC", msg.args[0] + ";" + std::to_string(oldPlayer->getCredits()) + ";" + std::to_string(oldPlayer->getRoomId()));
            Logger::info("Lobby: Player FD " + std::to_string(newFd) + " reconnected with nickname " + oldPlayer->getNickname());
            playerStateChanged = true;
            return;
        }

        if(player->getNickname() != msg.args[0] && player->getNickname() != ""){
            handleInvalidMessage(player);
            server.sendMessage(player->getFd(), "INV_MESS", "Already logged in");
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
            Logger::error("Lobby: LOGIN___ invalid nickname" + (msg.args[0].empty() ? "" : " (" + msg.args[0] + ")"));
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
            handleInvalidMessage(player);
            server.sendMessage(player->getFd(), "NACK_JON", "Missing room ID");
        }
    }
    else
    {
        handleInvalidMessage(player);
        Logger::error("Lobby: Player FD " + std::to_string(player->getFd()) + " sent invalid command " + msg.command);
    }
}

void Lobby::handleInvalidMessage(std::shared_ptr<Player> player)
{
    player->incrementInvalidMsg();
    Logger::error("Lobby: Player FD " + std::to_string(player->getFd()) + " sent invalid message");
    if (player->getInvalidMsgCount() > 5)
    {
        Logger::error("Lobby: Player FD " + std::to_string(player->getFd()) + " exceeded invalid message limit");
        server.sendMessage(player->getFd(), "DISCONNECT", "Too many invalid messages");
        destroyPlayer(player->getFd());
    }
}

void Lobby::destroyPlayer(int fd)
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
        players.erase(fd);
        dirtyPlayerState();
        Logger::debug("Lobby: Player destroyed on FD " + std::to_string(fd));
    }
}

bool Lobby::assignPlayerToRoom(std::shared_ptr<Player> player, int roomId)
{
    auto it = rooms.find(roomId);
    if (it != rooms.end() && it->second.getPlayerCount() < MAX_PLAYERS && it->second.getState() == GameState::WAITING_FOR_PLAYERS && player->getCredits() > 0)
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
