/**
 * Server for blackjack
 * Author: Marek Manzel
 * 
 * ClientConnection.h - Client connection handler for individual socket connections
 * Manages buffering of incoming data from clients and extracts complete messages
 * delimited by newlines. Handles partial message reception and reconstruction.
 */

#ifndef CLIENT_CONNECTION_H
#define CLIENT_CONNECTION_H

#include <string>
#include <vector>

class ClientConnection
{
public:
    ClientConnection(int fd);

    // Returns true if data was appended successfully
    // Returns true and buffer has content if '\n' was found
    bool appendBuffer(const char *data, size_t length);

    // Extracts full lines from the internal buffer
    std::vector<std::string> getMessages();

private:
    int socketFd;
    std::string buffer;
};

#endif