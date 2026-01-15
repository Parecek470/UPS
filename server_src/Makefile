CXX = g++
CXXFLAGS = -Wall -Wextra -pedantic -std=c++17 -g -I src
LDFLAGS = -pthread

SRC_DIRS = src src/core src/network src/protocol src/game
SRCS = $(foreach dir, $(SRC_DIRS), $(wildcard $(dir)/*.cpp))
OBJS = $(SRCS:.cpp=.o)
TARGET = blackjack_server

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)