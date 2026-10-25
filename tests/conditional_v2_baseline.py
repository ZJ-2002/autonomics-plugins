import hashlib
import json
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
BASELINE_REVISION = "f3715049facecc04abf8778ac71e01abb5b4b0e4"
IDENTITIES = {
    "research-adapters/cachexia-lcmm/manifest.toml": {
        "before": "f0f65466543377ff485c553c26a53650ad35718c3a59d99b4b532e260dbdc069",
        "current": "bc4d1528d4786bc15e687136ebb30419b672d8fa036989a9bf2c7875aef591de"
    },
    "research-adapters/cachexia-lcmm-typed-values/manifest.toml": {
        "before": "3f90183b96b13d9f18000ae42e71a87c22e115fa76ed8294d3bc47e559bfe62c",
        "current": "297e257f377461e5e6fe3b0f7c9205f6b9a2efe94615d3feb7abdd40fbeb3014"
    },
    "research-adapters/cachexia-mice/manifest.toml": {
        "before": "800c76164539b4d4b73ffc1a9dcda85f517709030476e063175a5f1465e434d2",
        "current": "5cf2039f05b904c572bb7b4479c0920ffdcd4e2a841787d9c77ffa86c2972e61"
    },
    "research-adapters/cachexia-mice-typed-values/manifest.toml": {
        "before": "63a57ac503ac19043835ed66d3939f908e623861e6d67e62a185dcad3613f515",
        "current": "5efd761bad8a174c8f1006b2b17850f3112f15d03487fe0b4b9a9a68870c06de"
    },
    "research-adapters/cachexia-survey/manifest.toml": {
        "before": "427bf8ec4d49496027ad888985ff8093032f2e5acc21a94cffe5c7eeb2949d9a",
        "current": "3bb30ca445a75be883073664ef536850a12a2384065e25eb8555a92b5f46afa8"
    },
    "research-adapters/cachexia-survey-typed-values/manifest.toml": {
        "before": "f48c9524ff0f5fb6dcd35b77cc241d88919d871a337c8bdc9ccc1c7ccb0aea15",
        "current": "0c08b2aea3675bfe640f97ea96b52f7e92a00955a2dcaad1fec20c14efa2b4b4"
    },
    "research-adapters/cachexia-lcmm/scripts/lcmm.R": {
        "before": "6a8b110fcaeebe5a64ab378f807777547907f222099783b5b62aa8c4e3db62f9",
        "current": "23039cbcca5734dd110fa7e01ce6412146a9923447ac3d6d912df40f82bc804a"
    },
    "research-adapters/cachexia-lcmm-typed-values/scripts/typed_values.py": {
        "before": "978ab903b9a50b1834ecc3ac6f87a824815fc84b915d1eb040ed09118bd8dd8f",
        "current": "322f9ce0ad3e139d43b77413c83d01cc7e1a7891788f3647b4ebd60fc5ca15ca"
    },
    "research-adapters/cachexia-mice/scripts/mice.R": {
        "before": "33d36247e60b0229965e1d2d559f91961888b7f959a82154a4996fbf4c10309e",
        "current": "302b2ce91d3a0c46b7146b5a8aab14b2e0faf7a867ea227b6ed8c44125868217"
    },
    "research-adapters/cachexia-mice/scripts/bind_contract.R": {
        "before": "77c1fd5bc3025d3e6c7c70dcbdf5945493194e6e6fefa261a737bba3f7adc14a",
        "current": "265995b924c0ae508da00d3e14ef327ab7ac2f0d3fffdc2da6f1cd22e9aee83b"
    },
    "research-adapters/cachexia-mice-typed-values/scripts/typed_values.py": {
        "before": "c503512f82c82ef7cf28950e0b64cbaf3e7ccf85f445ff0d11cf23a21b9189f8",
        "current": "29fd1688d1a1fdc8a8d9a7b08c2652910b1111dfb7b8ca31690fbc40d299ddf6"
    },
    "research-adapters/cachexia-survey/scripts/survey.R": {
        "before": "f7d6c2bee9abf84474aaf4b3a78e35769d2bb58867c3f1b9508c9b70761c7716",
        "current": "441908c41c1f6aabae4316913195e39696adaf2aa0c2e08cffbb2a3f92b577d9"
    },
    "research-adapters/cachexia-survey/scripts/bind_contract.R": {
        "before": "ee8a4ebd6a0d861a31de3d1d08a62b5c6aa953e1aa625e4dda3854ae2ab5b684",
        "current": "64c83187f184d49f44f7b52409d336054a574cb8cdbe6c551282bd6727e4aa4b"
    },
    "research-adapters/cachexia-survey-typed-values/scripts/typed_values.py": {
        "before": "ceff7a428fc10ef89bd27142a14e07968fc58cae49065113916d464c30d7e76c",
        "current": "d0ee8f5643e9bc4178ba5fba3235ca3f8a9b005597515e289ef38c5e17647a4e"
    }
}


def published_bytes(name):
    content = (ROOT / "tests/fixtures/conditional-v1" / name).read_bytes()
    if hashlib.sha256(content).hexdigest() != IDENTITIES[name]["before"]:
        raise AssertionError("Immutable published V1 source fixture changed: " + name)
    return content


def assert_current_source(test, name):
    test.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
                     IDENTITIES[name]["current"], name)


def assert_manifest_extension(test, family, count):
    name = "research-adapters/" + family + "/manifest.toml"
    original = tomllib.loads(published_bytes(name).decode())
    current = tomllib.loads((ROOT / name).read_text())
    test.assertEqual(current["image"], original["image"])
    test.assertEqual(len(original["nodes"]), count)
    test.assertEqual(current["nodes"][:count], original["nodes"])
    test.assertEqual(len(current["nodes"]), 2 * count)
    for prior, added in zip(original["nodes"], current["nodes"][count:]):
        test.assertEqual(added["kind"], prior["kind"] + "_v2")
        test.assertEqual(added["ports"], prior["ports"])
        test.assertEqual(added["resources"], prior["resources"])
        test.assertEqual(added["command"]["env"],
                         dict(prior["command"].get("env", {}),
                              AUTONOMICS_TECHNICAL_CONTRACT_VERSION="2"))
        test.assertEqual(added["command"]["script_file"], prior["command"]["script_file"])
    assert_current_source(test, name)

