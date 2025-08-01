# pyright: standard
########## Device Prefixes ##########

from enum import StrEnum


__all__ = ["Topics", "Tasmotas", "Onlyfans"]


class Topics(StrEnum):
    LUCE_PW = "LUCE-pw"
    PLUG_1 = "tasmota-plug-1"
    PLUG_2 = "tasmota-plug-2"
    PLUG_3 = "tasmota-plug-3"
    ONLYFANS = "onlyfans"
    TASMOTAS = "tasmotas"


class Tasmotas(StrEnum):
    LUCE_PW = Topics.LUCE_PW
    PLUG_1 = Topics.PLUG_1
    PLUG_2 = Topics.PLUG_2
    PLUG_3 = Topics.PLUG_3


class Onlyfans(StrEnum):
    PLUG_2 = Topics.PLUG_2
    PLUG_3 = Topics.PLUG_3
