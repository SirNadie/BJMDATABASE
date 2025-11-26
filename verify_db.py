
import sqlite3
from db_utils import get_db_connection

def test_connection_isolation():
    print("Testing connection isolation...")
    conn1 = get_db_connection()
    conn2 = get_db_connection()
    
    print(f"Connection 1: {conn1}")
    print(f"Connection 2: {conn2}")
    
    if conn1 is conn2:
        print("FAIL: Connections are the same object!")
    else:
        print("PASS: Connections are different objects.")
        
    conn1.close()
    conn2.close()

if __name__ == "__main__":
    test_connection_isolation()
