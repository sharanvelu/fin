class Color:
    # Font Colors
    clear = "\033[0m"
    red = "\033[38;5;196m"
    green = "\033[38;3;32m"
    white = "\033[1;37m"
    cyan = "\033[1;36m"
    

    # Font Styling
    bold = "\033[1m"
    underline = "\033[4m"
    italic = "\033[3m"

    # Process Indicator
    process = cyan + '=> ' + clear

    # Process Indicator
    error = red + '#### ' + clear
