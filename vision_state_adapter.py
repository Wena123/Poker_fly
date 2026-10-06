"""
Miejsce pod późniejszy moduł "prawdziwe życie -> stan symulatora".

Docelowo AI od obrazu może zwracać np.:

detected = {
    "hole_cards": ["AS", "KH"],
    "board": ["7D", "JC", "2S"],
    "pot": 120,
    "to_call": 30,
    ...
}

Ten moduł ma TYLKO tłumaczyć taki odczyt na ten sam format wejściowy,
którego używa brain podczas treningu. Brain nie musi wiedzieć,
czy dane pochodzą z symulatora czy z systemu vision.

Nie jest jeszcze podłączony do żadnego prawdziwego klienta pokera.
"""

def validate_detected_cards(hole_cards, board):
    cards = list(hole_cards) + list(board)
    if len(cards) != len(set(cards)):
        raise ValueError("Ta sama karta występuje więcej niż raz.")
    if len(hole_cards) != 2:
        raise ValueError("Texas Hold'em wymaga 2 kart własnych.")
    if len(board) > 5:
        raise ValueError("Board nie może mieć więcej niż 5 kart.")
    return True
