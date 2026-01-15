#ifndef PLAYER_H
#define PLAYER_H

#include <string>
#include <vector>

enum class PlayerState
{
    LOBBY,
    IN_GAMEROOM,
    TMP_DISCONNECTED,
    DISCONNECTED
};

class Player
{
public:
    Player(int socketFd)
        : fd(socketFd), state(PlayerState::LOBBY), invalidMsgCount(0), roomId(-1)
    {
        credits = 1000; // Default starting credits
        resetGameAttributes();
    }

    int getFd() const { return fd; }

    void setNickname(const std::string &n) { nickname = n; }
    std::string getNickname() const { return nickname; }
    void setState(PlayerState s) { state = s; }
    PlayerState getState() const { return state; }

    void incrementInvalidMsg() { invalidMsgCount++; }
    int getInvalidMsgCount() const { return invalidMsgCount; }
    int getRoomId() const { return roomId; }
    void setRoomId(int id) { roomId = id; }

    void setTurn(bool turn) { hasTurn = turn; }
    bool getTurn() const { return hasTurn; }

    void setReady(bool ready) { isReady = ready; }
    bool getReady() const { return isReady; }

    void setPlacedBet(bool bet) { placedBet = bet; }
    bool getPlacedBet() const { return placedBet; }
    void setBetAmount(int amount) { betAmount = amount; }
    int getBetAmount() const { return betAmount; }
    void addPlayerCard(const std::string &card) { playerCards.push_back(card); }
    const std::string getPlayerCards() const
    {
        std::string cards;
        if (playerCards.empty())
            return "NO";
        for (const auto &card : playerCards)
        {
            if (!cards.empty())
                cards += ";";
            cards += card;
        }
        return cards;
    }
    void clearPlayerCards() { playerCards.clear(); }
    int getCredits() const { return credits; }
    void setCredits(int amount) { credits = amount; }

    void resetGameAttributes()
    {
        hasTurn = false;
        isReady = false;
        placedBet = false;
        isWaiting = true;
        betAmount = 0;
        playerCards.clear();
    }

private:
    int fd;
    std::string nickname;
    PlayerState state;
    int invalidMsgCount;
    int roomId;
    int credits;

    // game-related attributes
    bool hasTurn;
    bool isReady;
    bool placedBet;
    int betAmount;
    std::vector<std::string> playerCards;
    bool isWaiting;
};

#endif