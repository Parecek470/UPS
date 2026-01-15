#include "Logger.h"
#include <ctime>
#include <vector>

std::mutex Logger::logMutex;

void Logger::log(LogLevel level, const std::string &message)
{
    std::lock_guard<std::mutex> lock(logMutex);

    std::time_t now = std::time(nullptr);
    char timeBuf[20];
    std::strftime(timeBuf, sizeof(timeBuf), "%Y-%m-%d %H:%M:%S", std::localtime(&now));

    std::string levelStr;
    switch (level)
    {
    case LogLevel::INFO:
        levelStr = "[INFO] ";
        break;
    case LogLevel::WARNING:
        levelStr = "[WARN] ";
        break;
    case LogLevel::ERROR:
        levelStr = "[ERR]  ";
        break;
    case LogLevel::DEBUG:
        levelStr = "[DEBUG]";
        break;
    }

    std::cout << timeBuf << " " << levelStr << message << std::endl;
}