#ifndef GAME_ROOM_H
#define GAME_ROOM_H

#define MAX_PLAYERS 7

#include <memory>
#include <string>
#include <vector>
#include <queue>
#include <chrono>
#include <mutex>
#include "game/Player.h"
#include "protocol/Message.h"

class TcpServer;

enum class GameState
{
    WAITING_FOR_PLAYERS,
    BETTING,
    PLAYING,
    ROUND_END
};

class GameRoom
{
public:
    GameRoom(int id);

    void ResetDefaultState();

    void addPlayer(std::shared_ptr<Player> player);

    void removePlayer(std::shared_ptr<Player> player);

    int getPlayerCount() const { return players.size(); }

    GameState getState() const { return gameState; }

    static void setServer(TcpServer *srv) { server = srv; }
    void broadcastMessage(const std::string &message, const std::string &args = "");
    void handle(std::shared_ptr<Player> player, const Message &msg);
    void handleStateWaitingForPlayers(std::shared_ptr<Player> player, const Message &msg);
    void handleStateBetting(std::shared_ptr<Player> player, const Message &msg);
    void handleStatePlaying(std::shared_ptr<Player> player, const Message &msg);
    void handleStateRoundEnd(std::shared_ptr<Player> player, const Message &msg);
    void handleInvalidMessage(std::shared_ptr<Player> player);

    bool areAllPlayersReady() const;
    bool placeBet(std::shared_ptr<Player> player, int amount);
    bool allPlayersPlacedBets() const;
    void update();
    std::string getRoomState() const;
    std::string getGameState() const;

    void startTurnTimer() { playerGotTurnTime = std::chrono::steady_clock::now(); }
    long getTurnElapsedSeconds() const
    {
        auto now = std::chrono::steady_clock::now();
        return std::chrono::duration_cast<std::chrono::seconds>(now - playerGotTurnTime).count();
    };

    void dealCards();
    std::string getDealerCards() const;
    void dealerPlay();
    std::string generateCard();
    int calculateHandValue(const std::string &cards) const;
    bool isTurnOver();
    bool playerHit(std::shared_ptr<Player> player);
    void playerStand(std::shared_ptr<Player> player);
    std::string getCredits(std::shared_ptr<Player> player) const;

private:
    std::mutex roomMutex;
    int roomId;
    std::vector<std::shared_ptr<Player>> players;
    static TcpServer *server;

    // Game state variables
    GameState gameState;
    std::vector<std::string> dealerCards;
    std::deque<std::shared_ptr<Player>> turnOrder;
    std::chrono::steady_clock::time_point playerGotTurnTime;
};

#endif // GAME_ROOM_H