from enum import Enum

# class syntax
class Color(Enum):
    RED = 0
    GREEN = 1
    BLUE = 2

# functional syntax
Color = Enum('Color',[('RED', 0), ('GREEN', 1), ('BLUE', 2)])

print(Color.RED)          # Color.RED
color = 1
print(Color(color))      # Color.RED

# print only name   
print(Color(color).name)     # RED