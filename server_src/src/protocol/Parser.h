/**
 * Server for blackjack
 * Author: Marek Manzel
 *
 * Parser.h - Protocol message parser for client commands
 * Parses incoming client messages according to the blackjack protocol format.
 * Validates message structure, extracts commands and arguments, and handles
 * protocol-specific formatting requirements.
 */

#ifndef PARSER_H
#define PARSER_H

#include "Message.h"
#include <core/Utils.h>
#include <sstream>
#include <algorithm>

class Parser
{
public:
    static Message parse(const std::string &rawLine)
    {
        Message msg;

        if (rawLine.empty())
        {
            return msg;
        }

        // Tokenize the string by delimiter ':'
        std::vector<std::string> tokens = Utils::splitString(rawLine, ':');

        // Validation: Must have Header and Command
        if (tokens.size() < 2)
        {
            return msg;
        }

        // First token must be "BJ"
        if (tokens[0] != "BJ")
        {
            return msg;
        }

        // Second token (Command) must be length 8, i first thought messages will be fixed length, now its not mendatory but still prevents when someone sends garbage
        std::string rawCommand = tokens[1];
        if (rawCommand.length() != 8)
        {
            return msg;
        }

        // Convert to Uppercase
        std::transform(rawCommand.begin(), rawCommand.end(), rawCommand.begin(),
                       [](unsigned char c)
                       { return std::toupper(c); });
        msg.command = rawCommand;

        // Add remaining tokens to args
        // skipping BJ and Command
        for (size_t i = 2; i < tokens.size(); ++i)
        {
            msg.args.push_back(tokens[i]);
        }

        // If we reached here, the message is valid
        msg.valid = true;
        return msg;
    }
};

#endif