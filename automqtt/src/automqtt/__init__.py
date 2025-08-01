# pyright: standard

import time
import paho.mqtt.client as mqtt
from paho.mqtt.reasoncodes import ReasonCode
from paho.mqtt.properties import Properties
from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion
from devices import *
from handlers import *
from mqttfs import *

########## Stateful handlers ##########


tasmotas_power = PowerStatusBehaviour(Topics.TASMOTAS, Tasmotas)
onlyfans_power = PowerStatusBehaviour(Topics.ONLYFANS, Onlyfans)
onlyfans_timer = TimerStatusBehaviour(Topics.ONLYFANS, 1, Onlyfans)

########## Handler table ##########

handler_tree: HandlerTree = {
    "stat": {
        "LUCE-pw": {
            "POWER": {"global-power": tasmotas_power.get_handler(Tasmotas.LUCE_PW)}
        },
        "tasmota-plug-1": {
            "POWER": {"global-power": tasmotas_power.get_handler(Tasmotas.PLUG_1)}
        },
        "tasmota-plug-2": {
            "POWER": {
                "global-power": tasmotas_power.get_handler(Tasmotas.PLUG_2),
                "onlyfans-power": onlyfans_power.get_handler(Onlyfans.PLUG_2),
            },
            "TIMER": {
                "retain": retain,
                "retained": {  # Publish
                    "unmarshalling_1": time_unmarshalled(1, Topics.PLUG_2),
                },
            },
            "TIMERS": {
                "retain": retain,
                "retained": {  # Publish
                    "unmarshalling_1": time_unmarshalled(1, Topics.PLUG_2),
                },
            },
            "TIMER1": {
                "unmarshalled": {  # Publish
                    "onlyfans-timer": onlyfans_timer.get_handler(Onlyfans.PLUG_2)
                },
            },
        },
        "tasmota-plug-3": {
            "POWER": {
                "global-power": tasmotas_power.get_handler(Tasmotas.PLUG_3),
                "onlyfans-power": onlyfans_power.get_handler(Onlyfans.PLUG_3),
            },
            "TIMER": {
                "retain": retain,
                "retained": {  # Publish
                    "unmarshalling_1": time_unmarshalled(1, Topics.PLUG_3),
                },
                "unmarshalled": {  # Publish
                    "onlyfans-timer": onlyfans_timer.get_handler(Onlyfans.PLUG_3)
                },
            },
            "TIMERS": {
                "retain": retain,
                "retained": {  # Publish
                    "unmarshalling_1": time_unmarshalled(1, Topics.PLUG_3),
                },
            },
            "TIMER1": {
                "unmarshalled": {  # Publish
                    "onlyfans-timer": onlyfans_timer.get_handler(Onlyfans.PLUG_3)
                },
            },
        },
        "onlyfans": {"POWER": {}, "TIMER1": {"unmarshalled": {}}},  # Publish only
        "tasmotas": {"POWER": {}},  # Publish only
    },
    "cmnd": {
        "tasmota-plug-2": {"Timer1": {}},  # Publish only
        "tasmota-plug-3": {"Timer1": {}},  # Publish only
        "onlyfans": {"Timer1": {}},  # Publish only
    },
    "cmnde": {
        "tasmota-plug-2": {"Timer1": {"marshalling": time_marshalled}},
        "tasmota-plug-3": {"Timer1": {"marshalling": time_marshalled}},
        "onlyfans": {"Timer1": {"marshalling": time_marshalled}},
    },
}


########## Service ##########


# The callback for when the client receives a CONNACK response from the server.
def on_connect(
    client: mqtt.Client,
    fs: MQTTPath,
    _flags: mqtt.ConnectFlags,
    reason_code: ReasonCode,
    _properties: Properties | None,
):
    print(f"Connected with result code {reason_code}")
    # Subscribe to all handled topics
    for path, _dirs, files in fs.walk():
        if len(files) > 0:
            print(f"Subscribing to {str(path.resolve())}")
            client.subscribe(str(path.resolve()))


counter = [0]
sum = [0]


# The callback for when a PUBLISH message is received from the server.
def on_message(client: mqtt.Client, fs: MQTTPath, msg: mqtt.MQTTMessage):
    for child in (fs / msg.topic).iterdir():
        if child.is_file():
            print(f"Firing {str(child.resolve())}")
            try:
                start = time.perf_counter_ns()
                child.handler(client, fs, msg)
                stop = time.perf_counter_ns()

                sum[0] += stop - start
                counter[0] += 1
                print(
                    f"Done in: {(stop-start)/1000}ms, avg: {sum[0] / (counter[0]*1000)}ms"
                )
            except FileNotFoundError as e:
                h: str = str(child.resolve())
                t: str = str(e.args[0].resolve())  # type: ignore
                print(
                    f'Error, No such topic or handler: handler "{h}" tried to access to "{t}" (not existent)'
                )
            except NotADirectoryError as e:
                h: str = str(child.resolve())
                t: str = str(e.args[0].resolve())  # type: ignore
                print(
                    f'Error, Not a topic: handler "{h}" tried to publish to topic "{t}" (an handler)'
                )
            except IsADirectoryError as e:
                h: str = str(child.resolve())
                t: str = str(e.args[0].resolve())  # type: ignore
                print(
                    f'Error, Not a topic: handler "{h}" tried to run handler "{t}" (a topic)'
                )


fs = MQTTPath(tree=handler_tree)


def main():
    mqttc = mqtt.Client(
        CallbackAPIVersion.VERSION2,
        protocol=MQTTProtocolVersion.MQTTv5,
        reconnect_on_failure=True,
        userdata=fs,
    )
    mqttc.username_pw_set(
        "automqtt",
        "b87d18800794d8778c8d48e55a335761f438846a13c9d41aee58ef270aee8779",
    )
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message

    mqttc.tls_set()  # type: ignore
    mqttc.connect("rico.mirolang.org", 8883, 60)

    # Blocking call that processes network traffic, dispatches callbacks and
    # handles reconnecting.
    # Other loop*() functions are available that give a threaded interface and a
    # manual interface.
    mqttc.loop_forever()


if __name__ == "__main__":
    main()
