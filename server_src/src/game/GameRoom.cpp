#include "GameRoom.h"
#include "../core/Logger.h"
#include "../network/TcpServer.h"
#include "../core/Utils.h"
#include <algorithm>

TcpServer *GameRoom::server = nullptr;

GameRoom::GameRoom(int id) : roomId(id)
{
    dealerCards = std::vector<std::string>();
    ResetDefaultState();
}

void GameRoom::ResetDefaultState()
{

    gameState = GameState::WAITING_FOR_PLAYERS;
    dealerCards.clear();
    turnOrder = std::deque<std::shared_ptr<Player>>();

    if (players.empty())
    {
        Logger::info("GameRoom: Room " + std::to_string(roomId) + " is already in default state");
        return;
    }
    for (auto &player : players)
    {
        player->resetGameAttributes();
    }

    Logger::info("GameRoom: Room " + std::to_string(roomId) + " reset to default state");
    update();
}

void GameRoom::broadcastMessage(const std::string &message, const std::string &args)
{
    for (const auto &player : players)
    {
        if (player->isOffline())
            continue;
        server->sendMessage(player->getFd(), message, args);
    }
}

bool GameRoom::allPlayersPlacedBets() const
{
    for (const auto &player : players)
    {
        if (!player->getPlacedBet())
        {
            return false;
        }
    }
    return true;
}

bool GameRoom::placeBet(std::shared_ptr<Player> player, int amount)
{
    if (amount > 0 && amount <= player->getCredits())
    {
        player->setCredits(player->getCredits() - amount);
        player->setBetAmount(amount);
        player->setPlacedBet(true);
        return true;
    }
    return false;
}

void GameRoom::update()
{
    // Gameloop update logic based on current game state
    switch (gameState)
    {
    case GameState::WAITING_FOR_PLAYERS:
        if (players.size() >= 1 && areAllPlayersReady())
        {
            gameState = GameState::BETTING;
            Logger::info("GameRoom: Room " + std::to_string(roomId) + " transitioning to BETTING state");
            server->lobby.dirtyPlayerState();
            // Notify players
            broadcastMessage("REQ_BET_");
        }
        break;

    case GameState::BETTING:
        // Handle betting logic here
        if (allPlayersPlacedBets())
        {
            gameState = GameState::PLAYING;
            server->lobby.dirtyPlayerState();
            Logger::info("GameRoom: Room " + std::to_string(roomId) + " transitioning to PLAYING state");
            // Notify players
            dealCards();
            startTurnTimer();
            broadcastMessage("GAMESTAT", getGameState());
        }
        break;

    case GameState::PLAYING:
        // Handle playing logic here
        if (isTurnOver())
        {
            gameState = GameState::ROUND_END;
            Logger::info("GameRoom: Room " + std::to_string(roomId) + " transitioning to ROUND_END state");
            dealerPlay();
            broadcastMessage("GAMESTAT", getGameState());
            // Notify players of round end and results
            for (const auto &player : players)
            {
                server->sendMessage(player->getFd(), "ROUNDEND", getCredits(player));
            }
        }
        else if (getTurnElapsedSeconds() >= 30)
        {
            // Auto-stand for current player
            auto currentPlayer = turnOrder.front();
            Logger::info("GameRoom: Player " + currentPlayer->getNickname() + " timed out in room " + std::to_string(roomId) + ", auto-standing");
            playerStand(currentPlayer);
            startTurnTimer(); // Reset timer for next player
            broadcastMessage("GAMESTAT", getGameState());
        }
        break;

    case GameState::ROUND_END:
        // Handle end of round logic here
        ResetDefaultState();
        gameState = GameState::WAITING_FOR_PLAYERS;
        server->lobby.dirtyPlayerState();
        Logger::info("GameRoom: Room " + std::to_string(roomId) + " transitioning to WAITING_FOR_PLAYERS state");
        break;
    }
}

std::string GameRoom::getCredits(std::shared_ptr<Player> player) const
{
    if (player == nullptr)
        return "CREDITS;0;BET;0";
    // evaluate credits and bet amount
    int handValue = calculateHandValue(player->getPlayerCards());
    int dealerValue = calculateHandValue(getDealerCards());
    int winnings = 0;

    if (handValue > 21 || (dealerValue <= 21 && dealerValue > handValue))
    {
        // player loses bet
        Logger::info("GameRoom: Player " + player->getNickname() + " lost the round in room " + std::to_string(roomId));
        winnings = -player->getBetAmount();
    }
    else if (handValue == dealerValue)
    {
        // push, return bet
        winnings = player->getBetAmount();
        player->setCredits(player->getCredits() + winnings);
        Logger::info("GameRoom: Player " + player->getNickname() + " pushed the round in room " + std::to_string(roomId));
    }
    else if (handValue == 21 && Utils::splitString(player->getPlayerCards(), ';').size() == 2)
    {
        // player wins 1.5 times the bet
        winnings = static_cast<int>(player->getBetAmount() * 1.5);
        player->setCredits(player->getCredits() + winnings);
        Logger::info("GameRoom: Player " + player->getNickname() + " got blackjack in room " + std::to_string(roomId));
    }
    else
    {
        // player wins, give double the bet
        winnings = player->getBetAmount() * 2;
        player->setCredits(player->getCredits() + winnings);
        Logger::info("GameRoom: Player " + player->getNickname() + " won the round in room " + std::to_string(roomId));
    }

    return std::to_string(player->getCredits()) + ";" + std::to_string(winnings);
}

void GameRoom::dealerPlay()
{
    int dealerSum = calculateHandValue(getDealerCards());
    while (dealerSum < 17)
    {
        dealerCards.push_back(generateCard());
        dealerSum = calculateHandValue(getDealerCards());
    }
}

void GameRoom::dealCards()
{
    dealerCards.clear();
    dealerCards.push_back(generateCard());
    dealerCards.push_back(generateCard());
    for (const auto &player : players)
    {
        player->clearPlayerCards();
        player->addPlayerCard(generateCard());
        player->addPlayerCard(generateCard());
        turnOrder.push_back(player);
    }
}

bool GameRoom::playerHit(std::shared_ptr<Player> player)
{
    if (player == nullptr || turnOrder.empty())
        return false;

    Logger::info("number of players in queue: " + std::to_string(turnOrder.size()));
    // Check if it's the player's turn
    if (turnOrder.front() != player)
        return false;

    // evaluate hit action here
    int sum = calculateHandValue(player->getPlayerCards());
    if (sum >= 21)
        return false; // Cannot hit if already 21 or bust

    player->addPlayerCard(generateCard());
    startTurnTimer();
    return true;
}

int GameRoom::calculateHandValue(const std::string &cards) const
{
    int sum = 0;
    int aces = 0;

    auto cardList = Utils::splitString(cards, ';');
    for (const auto &card : cardList)
    {
        std::string rank = card.substr(0, card.size() - 1); // Exclude suit
        if (rank == "A")
        {
            sum += 11;
            aces++;
        }
        else if (rank == "K" || rank == "Q" || rank == "J")
        {
            sum += 10; // Face cards are worth 10
        }
        else
        {
            sum += std::stoi(rank); // Numeric cards are worth their face value
        }
    }

    // Adjust for Aces
    while (sum > 21 && aces > 0)
    {
        sum -= 10; // Count Ace as 1 instead of 11
        aces--;
    }

    return sum;
}

void GameRoom::playerStand(std::shared_ptr<Player> player)
{
    if (player == nullptr || turnOrder.empty())
        return;

    // Check if it's the player's turn
    if (turnOrder.front() == player)
    {
        turnOrder.pop_front();
        startTurnTimer(); // Reset timer for next player
    }
}

bool GameRoom::isTurnOver()
{
    return turnOrder.empty();
}

std::string GameRoom::generateCard()
{
    // Example implementation: generate a random card
    const std::vector<std::string> suits = {"H", "D", "C", "S"};
    const std::vector<std::string> ranks = {"2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"};

    std::string suit = suits[rand() % suits.size()];
    std::string rank = ranks[rand() % ranks.size()];

    return rank + suit;
}

std::string GameRoom::getDealerCards() const
{
    std::string cards;
    if (dealerCards.empty())
        return "NO";
    for (const auto &card : dealerCards)
    {
        if (!cards.empty())
            cards += ";";
        cards += card;
    }
    return cards;
}

// corection of turn state and creating game state string
std::string GameRoom::getGameState() const
{
    std::string state = "D;" + getDealerCards() + ":";
    for (const auto &player : players)
    {
        player->setTurn(false);
        if (player == turnOrder.front())
        {

            player->setTurn(true);
        }
        state += "P;" + player->getNickname() + ";" + (player->isOffline() ? "2" : (player->getTurn() ? "1" : "0")) +
                 ";" + player->getPlayerCards() + ":";
    }
    return state;
}

void GameRoom::addPlayer(std::shared_ptr<Player> player)
{
    if (players.size() < MAX_PLAYERS)
    {
        players.push_back(player);
        Logger::info("GameRoom: Player added to room " + std::to_string(roomId));
    }
    else
    {
        Logger::error("GameRoom: Room " + std::to_string(roomId) + " is full");
    }
}

void GameRoom::removePlayer(std::shared_ptr<Player> player)
{
    auto it = std::find(players.begin(), players.end(), player);
    if (it != players.end())
    {
        if (player == turnOrder.front()) // If the player being removed has the turn, artificially end their turn
        {
            playerStand(player);
            broadcastMessage("GAMESTAT", getGameState());
        }
        else
        {
            // Just remove from turn order if not the current turn
            turnOrder.erase(std::remove(turnOrder.begin(), turnOrder.end(), player), turnOrder.end());
        }
        player->setRoomId(-1);
        player->setState(PlayerState::LOBBY);
        player->resetGameAttributes();
        players.erase(it);
        Logger::info("GameRoom: Player removed from room " + std::to_string(roomId));
    }
}

bool GameRoom::areAllPlayersReady() const
{
    for (const auto &player : players)
    {
        if (player == nullptr)
            continue;
        if (!player->getReady())
        {
            return false;
        }
    }
    return true;
}

std::string GameRoom::getRoomState() const
{
    std::string state = "";

    for (const auto &player : players)
    {
        if (player == nullptr)
            continue;
        state += "P;" + player->getNickname() + ";" + (player->isOffline() ? "2" : (player->getReady() ? "1" : "0")) +
                 ";BET;" + std::to_string(player->getBetAmount()) + ":";
    }

    return state;
}

void GameRoom::handleStateWaitingForPlayers(std::shared_ptr<Player> player, const Message &msg)
{
    if (msg.command == "RDY_____")
    {
        player->setReady(true);
        Logger::info("GameRoom: Player " + player->getNickname() + " is ready in room " + std::to_string(roomId));
        server->sendMessage(player->getFd(), "ACK__RDY", " ");
        return;
    }
    else if (msg.command == "NRD_____")
    {
        player->setReady(false);
        Logger::info("GameRoom: Player " + player->getNickname() + " is not ready in room " + std::to_string(roomId));
        server->sendMessage(player->getFd(), "ACK__NRD", " ");
        return;
    }
    else if (msg.command == "PAG_____")
    {
        if (player->getCredits() <= 0)
        {
            server->sendMessage(player->getFd(), "NACK_PAG", "Insufficient credits to continue");
            Logger::info("GameRoom: Player " + player->getNickname() + " cannot prepare for next game due to insufficient credits in room " + std::to_string(roomId));
            return;
        }
        Logger::info("GameRoom: Player " + player->getNickname() + " is preparing for next game in room " + std::to_string(roomId));
        update();
        server->sendMessage(player->getFd(), "ACK__PAG", std::to_string(roomId));
        return;
    }
    else
    {
        handleInvalidMessage(player);
        server->sendMessage(player->getFd(), "NACK_CMD", "Invalid command during WAITING_FOR_PLAYERS");
    }
}

void GameRoom::handleStateBetting(std::shared_ptr<Player> player, const Message &msg)
{
    // Handle messages specific to BETTING state
    if (msg.command == "BT______")
    {
        // Example: Process bet amount from msg.args
        if (msg.args.size() >= 1)
        {
            int betAmount = 0;
            try
            {
                betAmount = std::stoi(msg.args[0]);
            }
            catch (const std::exception &e)
            {
                server->sendMessage(player->getFd(), "NACK__BT", "Invalid bet amount");
                return;
            }

            if (placeBet(player, betAmount))
            {
                Logger::info("GameRoom: Player " + player->getNickname() + " placed a bet of " + std::to_string(betAmount) + " in room " + std::to_string(roomId));
                server->sendMessage(player->getFd(), "ACK___BT", " " + std::to_string(betAmount));
            }
            else
            {
                server->sendMessage(player->getFd(), "NACK__BT", "Invalid bet amount");
                Logger::info("GameRoom: Player " + player->getNickname() + " attempted invalid bet of " + std::to_string(betAmount) + " in room " + std::to_string(roomId));
            }
            return;
        }
    }
    else
    {
        handleInvalidMessage(player);
        server->sendMessage(player->getFd(), "NACK_CMD", "Invalid command during BETTING");
    }
}

void GameRoom::handleStatePlaying(std::shared_ptr<Player> player, const Message &msg)
{
    // Handle messages specific to PLAYING state
    if (msg.command == "HIT_____")
    {
        Logger::info("GameRoom: Player " + player->getNickname() + " requested HIT in room " + std::to_string(roomId));
        if (playerHit(player))
        {
            Logger::info("GameRoom: Player " + player->getNickname() + " received a new card in room " + std::to_string(roomId));
        }
        else
        {
            server->sendMessage(player->getFd(), "NACK_HIT", "Cannot hit at this time");
        }

        if (calculateHandValue(player->getPlayerCards()) > 21)
        {
            Logger::info("GameRoom: Player " + player->getNickname() + " busted in room " + std::to_string(roomId));
            playerStand(player); // Automatically stand if busted
            server->sendMessage(player->getFd(), "BUST____", " ");
        }
        else if (calculateHandValue(player->getPlayerCards()) == 21)
        {
            Logger::info("GameRoom: Player " + player->getNickname() + " hit 21 in room " + std::to_string(roomId));
            playerStand(player); // Automatically stand if hit 21
            server->sendMessage(player->getFd(), "HIT21___", " ");
        }
        return;
    }
    else if (msg.command == "STAND___")
    {
        Logger::info("GameRoom: Player " + player->getNickname() + " requested STAND in room " + std::to_string(roomId));
        playerStand(player);
        server->sendMessage(player->getFd(), "ACK_STND", " ");
        return;
    }
    else
    {
        handleInvalidMessage(player);
        server->sendMessage(player->getFd(), "NACK_CMD", "Invalid command during PLAYING");
    }
}

void GameRoom::handleStateRoundEnd(std::shared_ptr<Player> player, const Message &msg)
{
    // Handle messages specific to ROUND_END state
    if (msg.command == "PAG_____")
    {
        if (player->getCredits() <= 0)
        {
            server->sendMessage(player->getFd(), "NACK_PAG", "Insufficient credits to continue");
            Logger::info("GameRoom: Player " + player->getNickname() + " cannot prepare for next game due to insufficient credits in room " + std::to_string(roomId));
            return;
        }
        Logger::info("GameRoom: Player " + player->getNickname() + " is preparing for next game in room " + std::to_string(roomId));
        update();
        server->sendMessage(player->getFd(), "ACK__PAG", std::to_string(roomId));
        return;
    }
    else
    {
        handleInvalidMessage(player);
        server->sendMessage(player->getFd(), "NACK_CMD", "Invalid command during ROUND_END");
    }
}

void GameRoom::handleInvalidMessage(std::shared_ptr<Player> player)
{
    player->incrementInvalidMsg();
    if (player->getInvalidMsgCount() > 5)
    {
        Logger::error("GameRoom: Player " + player->getNickname() + " exceeded invalid message limit in room " + std::to_string(roomId));
        server->sendMessage(player->getFd(), "DISCONNECT", "Too many invalid messages");
        removePlayer(player);
        server->lobby.destroyPlayer(player->getFd());
    }
}

void GameRoom::handle(std::shared_ptr<Player> player, const Message &msg)
{
    std::lock_guard<std::mutex> lock(roomMutex);

    Logger::debug("GameRoom: Handling message " + msg.command + " from player " + player->getNickname() + " in room " + std::to_string(roomId));

    // reconnection of offline player
    if (msg.command == "REC__GAM")
    {
        if (gameState == GameState::PLAYING)
        {
            Logger::info("GameRoom: Player " + player->getNickname() + " reconnected during PLAYING state in room " + std::to_string(roomId));
            broadcastMessage("GAMESTAT", getGameState());
        }
        else
        {
            Logger::info("GameRoom: Player " + player->getNickname() + " reconnected during BETTING state in room " + std::to_string(roomId));
            broadcastMessage("ROMSTAUP", getRoomState());
        }
        return;
    }

    // Handle game-specific messages here
    switch (gameState)
    {
    case GameState::WAITING_FOR_PLAYERS:
        handleStateWaitingForPlayers(player, msg);
        broadcastMessage("ROMSTAUP", getRoomState());
        break;
    case GameState::BETTING:
        handleStateBetting(player, msg);
        broadcastMessage("ROMSTAUP", getRoomState());
        break;

    case GameState::PLAYING:
        handleStatePlaying(player, msg);
        broadcastMessage("GAMESTAT", getGameState());
        break;
    case GameState::ROUND_END:
        handleStateRoundEnd(player, msg);
        broadcastMessage("ROMSTAUP", getRoomState());
        break;

    default:
        break;
    }
    update();
}