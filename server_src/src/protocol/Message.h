/**
 * Server for blackjack
 * Author: Marek Manzel
 * 
 * Message.h - Protocol message structure definition
 * Defines the Message structure used to represent parsed client commands
 * with a command string, arguments vector, and validity flag.
 */

#ifndef MESSAGE_H
#define MESSAGE_H

#include <string>
#include <vector>

// Structure representing a parsed command: "CMD arg1 arg2"
struct Message
{
    std::string command;
    std::vector<std::string> args;
    bool valid;

    Message() : valid(false) {}
};

#endif