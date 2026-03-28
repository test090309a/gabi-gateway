import os

def path_corrector(data):
    # Wir suchen nach dem 'file_path' in den Tool-Argumenten
    if "messages" in data:
        for message in data["messages"]:
            if "tool_calls" in message:
                for tool in message["tool_calls"]:
                    args = tool.get("function", {}).get("parameters", {})
                    path = args.get("file_path", "")
                    
                    # Fix: Entferne führende Slashes und korrigiere 'gateway' Pfade
                    if path.startswith("/gateway/"):
                        args["file_path"] = path.replace("/gateway/", "", 1)
                    elif path.startswith("/"):
                        args["file_path"] = path[1:]
                        
                    # Fix: Ersetze Vorwärts-Slashes durch Backslashes für Windows
                    args["file_path"] = args["file_path"].replace("/", "\\")
    return data