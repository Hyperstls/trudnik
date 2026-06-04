import paramiko
import time

# PythonAnywhere SSH credentials
HOSTNAME = "hyperstls.pythonanywhere.com"
USERNAME = "hyperstls"
PASSWORD = "Hyperstls2024!"  # Используем временный пароль для теста

# Команда для выполнения
COMMANDS = [
    "cd ~/mysite",
    "git status",
    "git log --oneline -5",
]

try:
    # Create SSH client
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    # Connect
    print(f"Connecting to {HOSTNAME}...")
    ssh.connect(HOSTNAME, username=USERNAME, password=PASSWORD, timeout=10)
    print("Connected successfully!")
    
    # Execute commands
    for cmd in COMMANDS:
        print(f"\nExecuting: {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        # Wait for command to complete
        time.sleep(2)
        
        # Get output
        output = stdout.read().decode()
        error = stderr.read().decode()
        
        if output:
            print(f"Output:\n{output}")
        if error:
            print(f"Error:\n{error}")
    
    # Close connection
    ssh.close()
    print("\nConnection closed.")
    
except Exception as e:
    print(f"Exception: {e}")
    print("\nПопробуйте использовать другую авторизацию (SSH key или веб-интерфейс)")
