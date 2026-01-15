#ifndef PARSER_H
#define PARSER_H

#include "Message.h"
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

        // 2. Tokenize the string by delimiter ':'
        std::vector<std::string> tokens;
        std::stringstream ss(rawLine);
        std::string segment;

        while (std::getline(ss, segment, ':'))
        {
            tokens.push_back(segment);
        }

        // Validation: Must have Header and Command
        if (tokens.size() < 2)
        {
            return msg;
        }

        // 4. Validation: First token must be "BJ"
        if (tokens[0] != "BJ")
        {
            return msg;
        }

        // 5. Validation: Second token (Command) must be length 8
        std::string rawCommand = tokens[1];
        if (rawCommand.length() != 8)
        {
            return msg;
        }

        // 6. Process Command: Convert to Uppercase
        std::transform(rawCommand.begin(), rawCommand.end(), rawCommand.begin(),
                       [](unsigned char c)
                       { return std::toupper(c); });
        msg.command = rawCommand;

        // 7. Process Arguments: Add remaining tokens to args
        // Start from index 2 (skipping BJ and Command)
        for (size_t i = 2; i < tokens.size(); ++i)
        {
            msg.args.push_back(tokens[i]);
        }

        // 8. If we reached here, the message is valid
        msg.valid = true;
        return msg;
    }
};

#endif