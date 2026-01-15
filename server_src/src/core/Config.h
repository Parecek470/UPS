#ifndef CONFIG_H
#define CONFIG_H

struct Config
{
    int port;
    int rooms;

    // Defaults: Port 10000, 6 rooms max
    Config() : port(10000), rooms(6) {}
};

#endif