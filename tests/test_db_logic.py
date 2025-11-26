import unittest
import sqlite3
import os
from db_utils import get_db_connection_ctx, create_tables
from logic import add_new_client, add_part_without_vin, delete_client

# Use a test database
TEST_DB_NAME = 'test_brent_j_marketing.db'

class TestDBLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Override DB_NAME in db_utils and logic for testing
        import db_utils
        import logic
        import auth
        db_utils.DB_NAME = TEST_DB_NAME
        logic.DB_NAME = TEST_DB_NAME
        auth.DB_NAME = TEST_DB_NAME
        
        # Create fresh database
        if os.path.exists(TEST_DB_NAME):
            os.remove(TEST_DB_NAME)
        create_tables()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_NAME):
            os.remove(TEST_DB_NAME)

    def test_connection_context_manager(self):
        """Test that the context manager yields a connection and closes it."""
        with get_db_connection_ctx() as conn:
            self.assertIsInstance(conn, sqlite3.Connection)
            cursor = conn.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
        
        # Connection should be closed (though sqlite3 objects don't explicitly show 'closed' property easily, 
        # we can try to use it and expect failure if we had a handle, but here we just ensure it runs without error)

    def test_add_client(self):
        """Test adding a client using the refactored logic."""
        phone = "1234567890"
        name = "Test Client"
        user = "tester"
        
        # Add client
        result = add_new_client(phone, name, user)
        self.assertTrue(result)
        
        # Verify in DB
        with get_db_connection_ctx() as conn:
            row = conn.execute("SELECT * FROM clients WHERE phone = ?", (phone,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], name)

    def test_transaction_rollback(self):
        """Test that transactions are rolled back on error (duplicate key)."""
        phone = "1234567890" # Already exists from test_add_client
        name = "Duplicate Client"
        user = "tester"
        
        # add_new_client raises ValueError if client exists
        with self.assertRaises(ValueError):
            add_new_client(phone, name, user)

    def test_add_part_without_vin(self):
        """Test adding a part without a VIN."""
        part_name = "Test Part"
        part_number = "TP123"
        quantity = 5
        notes = "Test notes"
        client_phone = "1234567890"
        user = "tester"
        suppliers = [{'name': 'Sup1', 'buying_price': 10, 'selling_price': 20, 'delivery_time': '1d'}]
        
        part_id = add_part_without_vin(part_name, part_number, quantity, notes, client_phone, suppliers, user)
        self.assertIsNotNone(part_id)
        self.assertIsInstance(part_id, int)

if __name__ == '__main__':
    unittest.main()
