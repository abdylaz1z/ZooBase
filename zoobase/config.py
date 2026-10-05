"""Константы приложения ZooBase."""

DB_FILENAME = "zoobase.db"
DATE_FMT = "%d.%m.%Y"

BREEDS = ("arashan", "alatoo", "other")
SEXES = ("male", "female")
STATUSES = ("active", "quarantine", "pregnant", "for_sale", "sold", "culled", "dead")
LIVE_STATUSES = ("active", "quarantine", "pregnant", "for_sale")
HEALTH_KINDS = ("vaccine", "parasite", "disease", "note")
REPRO_KINDS = ("mating", "lambing")
GESTATION_DAYS = 150   # срок суягности: от случки до ожидаемого ягнения
PEDIGREE_DEPTH = 3     # родословная: родители, деды/бабки, прадеды/прабабки

SOON_DAYS = 7      # горизонт ленты задач
WARN_DAYS = 3      # жёлтый индикатор: событие в ближайшие N дней
LIST_LIMIT = 300   # максимум карточек в списке (для плавности на слабых телефонах)

RED = (0.86, 0.22, 0.20, 1)
YELLOW = (0.96, 0.69, 0.10, 1)
GREEN = (0.18, 0.64, 0.30, 1)
GREY = (0.55, 0.55, 0.55, 1)
