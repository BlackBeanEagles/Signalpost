import re


class InvalidOrganizationNumber(ValueError):
    pass


def normalize_orgnr(value: str) -> str:
    orgnr = re.sub(r"\s", "", str(value))
    if not re.fullmatch(r"\d{9}", orgnr):
        raise InvalidOrganizationNumber("Norwegian organisation numbers must contain exactly 9 digits")
    if not is_valid_orgnr(orgnr):
        raise InvalidOrganizationNumber("Organisation number failed the Norwegian Modulus 11 check")
    return orgnr


def is_valid_orgnr(orgnr: str) -> bool:
    if not re.fullmatch(r"\d{9}", str(orgnr)):
        return False
    weights = (3, 2, 7, 6, 5, 4, 3, 2)
    remainder = sum(int(digit) * weight for digit, weight in zip(orgnr[:8], weights)) % 11
    check = 11 - remainder
    if check == 11:
        check = 0
    if check == 10:
        return False
    return check == int(orgnr[8])


def assert_same_entity(requested: str, payload: dict) -> None:
    returned = str(payload.get("organisasjonsnummer", ""))
    if returned != requested:
        raise ValueError(f"Identity mismatch: requested {requested}, source returned {returned or 'none'}")

