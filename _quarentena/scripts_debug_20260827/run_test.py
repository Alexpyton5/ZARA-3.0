import sys
sys.path.insert(0, '/c/Users/alexp/Downloads/ZARA 3.0 CLEAN 002')
from core.aprendizado import _forma_do_pedido
print(repr(_forma_do_pedido('aumentar volume')))
print(repr(_forma_do_pedido('aumenta esse volume')))
print(repr(_forma_do_pedido('sobe o volume')))
