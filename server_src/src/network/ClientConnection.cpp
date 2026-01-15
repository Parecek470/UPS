#include "ClientConnection.h"

ClientConnection::ClientConnection(int fd) : socketFd(fd) {}

bool ClientConnection::appendBuffer(const char *data, size_t length)
{
    buffer.append(data, length);
    // Simple check: is there a newline?
    return buffer.find('\n') != std::string::npos;
}

std::vector<std::string> ClientConnection::getMessages()
{
    std::vector<std::string> messages;
    size_t pos;

    // Extract all complete lines ending in \n
    while ((pos = buffer.find('\n')) != std::string::npos)
    {
        std::string msg = buffer.substr(0, pos);

        // Handle Windows-style \r\n
        if (!msg.empty() && msg.back() == '\r')
        {
            msg.pop_back();
        }

        if (!msg.empty())
        {
            messages.push_back(msg);
        }

        buffer.erase(0, pos + 1);
    }
    return messages;
}