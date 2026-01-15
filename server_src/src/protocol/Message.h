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