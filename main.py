from configparser import ConfigParser
from tophatbot import Psych210Bot


def main():
    config = ConfigParser()
    config.read('credentials.cfg')
    username = config['credentials']['username']
    password = config['credentials']['password']

    bot = Psych210Bot(username, password)
    bot.list_questions()


if __name__ == '__main__':
    main()
