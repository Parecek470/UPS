#ifndef LOGGER_H
#define LOGGER_H

#include <string>
#include <mutex>
#include <iostream>

enum class LogLevel
{
    INFO,
    WARNING,
    ERROR,
    DEBUG
};

class Logger
{
public:
    static void log(LogLevel level, const std::string &message);
    static void error(const std::string &message) { log(LogLevel::ERROR, message); }
    static void info(const std::string &message) { log(LogLevel::INFO, message); }
    static void debug(const std::string &message) { log(LogLevel::DEBUG, message); }

private:
    static std::mutex logMutex;
};

#endif