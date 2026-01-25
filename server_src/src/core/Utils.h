/**
 * Server for blackjack
 * Author: Marek Manzel
 *
 * Utils.h - Utility functions for the blackjack server
 * Contains helper methods for nickname validation and string manipulation.
 */

#ifndef UTILS_H
#define UTILS_H

#include <string>
#include <vector>
#include <sstream>

class Utils
{
public:
    // Validates a nickname longer than 3 and less than 10 characters
    // and only containing alphanumeric characters, underscores, or hyphens
    static bool validateNickname(const std::string &nickname)
    {
        if (nickname.length() < 3 || nickname.length() > 10)
            return false;

        for (char c : nickname)
        {
            if (!isalnum(c) && c != '_' && c != '-')
                return false;
        }
        return true;
    }

    // splits a string by a delimiter and returns a vector of substrings
    static std::vector<std::string> splitString(const std::string &str, char delimiter)
    {
        std::vector<std::string> tokens;
        std::stringstream ss(str);
        std::string token;
        while (std::getline(ss, token, delimiter))
        {
            tokens.push_back(token);
        }
        return tokens;
    }
};

#endif