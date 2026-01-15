import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
import sys
import os

# Ensure app modules can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.core.license_manager import LicenseManager
except ImportError:
    # If run directly from root, might need adjustment
    sys.path.append(os.getcwd())
    from app.core.license_manager import LicenseManager

class KeyGenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Uni-Video Key Generator")
        self.root.geometry("500x350")
        
        # Hardware ID Input
        tk.Label(root, text="Target Hardware ID:", font=("Arial", 10, "bold")).pack(pady=5)
        self.hwid_entry = tk.Entry(root, width=50)
        self.hwid_entry.pack(pady=5)
        
        # Duration Input
        tk.Label(root, text="Duration (Days):", font=("Arial", 10, "bold")).pack(pady=5)
        self.days_entry = tk.Entry(root, width=20)
        self.days_entry.insert(0, "30") # Default 30 days
        self.days_entry.pack(pady=5)
        
        # Generate Button
        tk.Button(root, text="Generate Key", command=self.generate_key, bg="#4CAF50", fg="white", font=("Arial", 12)).pack(pady=15)
        
        # Output Area
        tk.Label(root, text="Generated Key:", font=("Arial", 10, "bold")).pack(pady=5)
        self.key_output = tk.Text(root, height=5, width=50)
        self.key_output.pack(pady=5)
        
        # Copy Button
        tk.Button(root, text="Copy to Clipboard", command=self.copy_key).pack(pady=5)

    def generate_key(self):
        hwid = self.hwid_entry.get().strip()
        days_str = self.days_entry.get().strip()
        
        if not hwid:
            messagebox.showerror("Error", "Please enter a Hardware ID")
            return
            
        try:
            days = int(days_str)
            expiry_date = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")
            
            key = LicenseManager.generate_key(hwid, expiry_date)
            
            self.key_output.delete("1.0", tk.END)
            self.key_output.insert("1.0", key)
            
        except ValueError:
            messagebox.showerror("Error", "Days must be a number")
        except Exception as e:
            messagebox.showerror("Error", f"Generation Failed: {e}")

    def copy_key(self):
        key = self.key_output.get("1.0", tk.END).strip()
        if key:
            self.root.clipboard_clear()
            self.root.clipboard_append(key)
            messagebox.showinfo("Success", "Key copied to clipboard!")

if __name__ == "__main__":
    root = tk.Tk()
    app = KeyGenApp(root)
    root.mainloop()
