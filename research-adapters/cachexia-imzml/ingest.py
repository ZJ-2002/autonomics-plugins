"""Lossless full imzML arrays, explicit measurement sums and immutable pair checks."""

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zlib

KEYS = {"schema_version", "scope", "test_id", "input_sha256", "expected_uuid", "expected_pixels", "windows", "specimen_identity", "coordinate_policy", "intensity_policy", "mass_policy", "window_policy", "summary_policy", "detection_policy", "row_unit", "source_pair_policy", "binary_policy", "max_input_bytes", "max_spectra", "max_peaks_per_spectrum", "max_total_peaks", "max_windows", "max_encoded_bytes_per_array"}
NAMES = ["pixels.parquet", "windows.parquet", "spectra.parquet", "pixel_windows.parquet", "audit.json", "request_ledger.tsv", "imzml.log", "source.imzML", "source.ibd"]
NS = "{http://psi.hupo.org/ms/mzml}"
FORMATS = {"MS:1000520": ("float16", "e", 2), "MS:1000521": ("float32", "f", 4), "MS:1000523": ("float64", "d", 8), "MS:1000519": ("int32", "i", 4), "MS:1000522": ("int64", "q", 8)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(filename, algorithm="sha256"):
    value = hashlib.new(algorithm)
    with Path(filename).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""): value.update(block)
    return value.hexdigest()


def lexical(value):
    return isinstance(value, str) and bool(value.strip()) and not any(char in value for char in "\t\r\n\x00")


def recover_test_id(raw):
    decoder, identifiers = json.JSONDecoder(), []
    cursor = len(raw) - len(raw.lstrip())
    if not raw[cursor:].startswith("{"):
        return None
    cursor += 1
    try:
        while True:
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] == "}":
                break
            key, cursor = decoder.raw_decode(raw, cursor)
            if not isinstance(key, str):
                break
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] != ":":
                break
            cursor += 1
            while raw[cursor].isspace():
                cursor += 1
            value, cursor = decoder.raw_decode(raw, cursor)
            if key == "test_id":
                identifiers.append(value)
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] != ",":
                break
            cursor += 1
    except (ValueError, IndexError):
        pass
    return identifiers[0] if len(identifiers) == 1 and (identifiers[0] is None or isinstance(identifiers[0], str)) else None


def load_request(filename):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(filename).read_text(), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON constant")))


def validate(request):
    require(isinstance(request, dict) and set(request) == KEYS, "Exact frozen request keys required")
    require(type(request["schema_version"]) is int and request["schema_version"] == 1 and request["scope"] == "TECHNICAL_IMZML_NOT_G0", "Unknown frozen scope/schema")
    require(lexical(request["test_id"]), "Frozen test_id required")
    require(isinstance(request["input_sha256"], list) and len(request["input_sha256"]) == 2 and all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in request["input_sha256"]), "Two frozen content hashes required")
    require(isinstance(request["expected_uuid"], str) and str(uuid.UUID(request["expected_uuid"])) == request["expected_uuid"], "Canonical frozen UUID required")
    identity = request["specimen_identity"]
    require(isinstance(identity, dict) and set(identity) == {"donor_id", "organ", "slice_id"} and all(lexical(value) for value in identity.values()), "Frozen specimen identity required")
    pixels = request["expected_pixels"]
    require(isinstance(pixels, list) and bool(pixels), "Complete frozen pixel axis required")
    fields = {"spectrum_id", "spectrum_index", "x", "y", "z", "z_origin"}
    require(all(isinstance(row, dict) and set(row) == fields and lexical(row["spectrum_id"]) and all(type(row[name]) is int and -(1 << 63) <= row[name] < (1 << 63) for name in ["spectrum_index", "x", "y", "z"]) and row["spectrum_index"] >= 0 and row["z_origin"] in {"EXPLICIT", "PYIMZML_DEFAULT_ONE"} for row in pixels), "Complete typed pixel identity required")
    require(len({row["spectrum_id"] for row in pixels}) == len(pixels) and len({row["spectrum_index"] for row in pixels}) == len(pixels), "Duplicate spectrum identity/index")
    windows = request["windows"]
    require(isinstance(windows, list) and all(isinstance(row, dict) and set(row) == {"label", "lo", "hi"} and lexical(row["label"]) and all(type(row[name]) in [int, float] and math.isfinite(row[name]) for name in ["lo", "hi"]) and 0 <= row["lo"] < row["hi"] for row in windows), "Finite ordered window bounds required")
    require(len({row["label"] for row in windows}) == len(windows), "Duplicate window labels")
    policies = {"coordinate_policy": "SOURCE_XYZ_IMAGE_GRID_NO_PHYSICAL_CONVERSION", "intensity_policy": "FINITE_SIGNED_MEASUREMENT_WITH_EXACT_INTEGER_SHADOW", "mass_policy": "FINITE_NONNEGATIVE_ORDER_PRESERVED", "window_policy": "CLOSED_BOTH_ENDS_NO_PEAK_ANNOTATION", "summary_policy": "ALL_PIXELS_FSUM_FLOAT64_WITH_EXACT_INTEGER_NUMERATOR", "detection_policy": "SUMMED_WINDOW_SIGNAL_STRICTLY_POSITIVE", "row_unit": "SPECTRUM_OR_PIXEL_NOT_DONOR_INFERENCE", "source_pair_policy": "UUID_AND_ALL_DECLARED_CHECKSUMS_PLUS_CONTENT_HASH", "binary_policy": "IMZML1.1_LITTLE_ENDIAN_UNCOMPRESSED_OR_ZLIB"}
    require(all(request[key] == value for key, value in policies.items()), "Unsupported scientific/interface policy")
    for key in ["max_input_bytes", "max_spectra", "max_peaks_per_spectrum", "max_total_peaks", "max_windows", "max_encoded_bytes_per_array"]:
        require(type(request[key]) is int and request[key] > 0, "Positive frozen resource bound required: " + key)
    require(len(pixels) <= request["max_spectra"] and len(windows) <= request["max_windows"], "Frozen spectrum/window budget exceeded")


def cv(element, recursive=False):
    answer = {}
    for row in element.iter(NS + "cvParam") if recursive else element.findall(NS + "cvParam"):
        key = row.attrib["accession"]
        require(key not in answer, "Duplicate CV term: " + key)
        answer[key] = row.attrib.get("value", "")
    return answer


def xml_contract(xml, binary, request):
    raw = xml.read_bytes()
    require(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(), "XML DTD/entities are forbidden")
    root = ET.fromstring(raw)
    require(root.tag == NS + "mzML", "Expected imzML mzML root/namespace")
    content = root.find(NS + "fileDescription/" + NS + "fileContent")
    require(content is not None, "imzML fileContent required")
    terms = cv(content)
    require("IMS:1000080" in terms and str(uuid.UUID(terms["IMS:1000080"])) == request["expected_uuid"], "Frozen XML UUID differs")
    with binary.open("rb") as handle: header = handle.read(16)
    require(header == uuid.UUID(terms["IMS:1000080"]).bytes, "imzML/ibd UUID mismatch")
    checksums = {key: algorithm for key, algorithm in [("IMS:1000091", "sha1"), ("IMS:1000090", "md5")] if key in terms}
    require(checksums, "Declared ibd checksum required")
    require(all(terms[key].lower() == digest(binary, algorithm) for key, algorithm in checksums.items()), "Declared ibd checksum differs")
    modes = [key for key in ["IMS:1000030", "IMS:1000031"] if key in terms]
    require(len(modes) == 1, "Exactly one continuous/processed mode required")
    groups = {}
    for element in root.findall(NS + "referenceableParamGroupList/" + NS + "referenceableParamGroup"):
        require(element.attrib["id"] not in groups, "Duplicate reference group identity")
        groups[element.attrib["id"]] = cv(element)
    spectra = root.find(NS + "run/" + NS + "spectrumList")
    require(spectra is not None and len(spectra) == int(spectra.attrib["count"]) == len(request["expected_pixels"]), "Declared spectrum count differs")
    pixels, descriptors, total = [], [], 0
    for element in spectra:
        scan = element.find(NS + "scanList/" + NS + "scan")
        require(scan is not None, "Spectrum scan metadata required")
        position = cv(scan)
        row = {"spectrum_id": element.attrib["id"], "spectrum_index": int(element.attrib["index"]), "x": int(position["IMS:1000050"]), "y": int(position["IMS:1000051"]), "z": int(position.get("IMS:1000052", "1")), "z_origin": "EXPLICIT" if "IMS:1000052" in position else "PYIMZML_DEFAULT_ONE"}
        pixels.append(row)
        arrays = element.find(NS + "binaryDataArrayList")
        require(arrays is not None and len(arrays) == int(arrays.attrib["count"]) == 2, "Two spectral arrays required")
        descriptor = {}
        for array in arrays:
            combined = {}
            for ref in array.findall(NS + "referenceableParamGroupRef"):
                require(ref.attrib["ref"] in groups, "Unknown array reference group")
                for key, value in groups[ref.attrib["ref"]].items():
                    require(key not in combined, "Conflicting inherited array CV term")
                    combined[key] = value
            local = cv(array)
            require(not set(local) & set(combined), "Conflicting direct/inherited array CV term")
            combined.update(local)
            roles = [key for key in ["MS:1000514", "MS:1000515"] if key in combined]
            precision = [key for key in FORMATS if key in combined]
            compression = [key for key in ["MS:1000574", "MS:1000576"] if key in combined]
            require(len(roles) == len(precision) == len(compression) == 1 and combined.get("IMS:1000101") == "true", "Unambiguous external array format required")
            role = "mz" if roles[0] == "MS:1000514" else "intensity"
            require(role not in descriptor, "Duplicate spectral array role")
            offset, length, encoded = [int(combined[key]) for key in ["IMS:1000102", "IMS:1000103", "IMS:1000104"]]
            require(offset >= 16 and 0 <= length <= request["max_peaks_per_spectrum"] and 0 <= encoded <= request["max_encoded_bytes_per_array"] and offset + encoded <= binary.stat().st_size, "Spectral offset/length or budget invalid")
            descriptor[role] = {"offset": offset, "length": length, "encoded": encoded, "precision": precision[0], "zlib": compression[0] == "MS:1000574"}
        require(set(descriptor) == {"mz", "intensity"} and descriptor["mz"]["length"] == descriptor["intensity"]["length"], "m/z and intensity lengths differ")
        total += descriptor["mz"]["length"]
        require(total <= request["max_total_peaks"], "Frozen total peak budget exceeded")
        descriptors.append(descriptor)
    require(pixels == request["expected_pixels"], "Frozen full pixel axis differs")
    require(len({row["mz"]["precision"] for row in descriptors}) == len({row["intensity"]["precision"] for row in descriptors}) == 1, "Mixed precision arrays require a new explicit schema contract")
    if modes[0] == "IMS:1000030":
        require(all(row["mz"] == descriptors[0]["mz"] for row in descriptors), "Continuous mode must share the mass axis")
    return pixels, descriptors, terms


def decode(handle, descriptor):
    import numpy as np
    dtype, code, size = FORMATS[descriptor["precision"]]
    expected = descriptor["length"] * size
    handle.seek(descriptor["offset"])
    raw = handle.read(descriptor["encoded"])
    require(len(raw) == descriptor["encoded"], "Truncated encoded spectral data")
    if descriptor["zlib"]:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(raw, expected + 1)
        require(decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data, "Compressed array not complete single bounded zlib stream")
    require(len(raw) == expected, "Decoded array byte length differs")
    return np.frombuffer(raw, dtype=np.dtype(dtype).newbyteorder("<"))


def signal(values, integer=False):
    require(all(math.isfinite(value) for value in values), "Nonfinite spectral signal")
    exact = sum(int(value) for value in values) if integer else None
    floating = float(exact) if exact is not None else math.fsum(values)
    require(math.isfinite(floating), "Nonfinite signal sum")
    return floating, str(exact) if exact is not None else None


def arrow_type(precision):
    import pyarrow as pa
    return {"MS:1000520": pa.float32(), "MS:1000521": pa.float32(), "MS:1000523": pa.float64(), "MS:1000519": pa.int32(), "MS:1000522": pa.int64()}[precision]


def calculate(inputs, request, folder):
    import importlib.metadata
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pyimzml.ImzMLParser import ImzMLParser
    require(importlib.metadata.version("pyimzml") == "1.5.5" and sys.byteorder == "little", "Frozen parser version/little-endian runtime differs")
    require(all(filename.stat().st_size <= request["max_input_bytes"] for filename in inputs), "Frozen input byte budget exceeded")
    require([digest(filename) for filename in inputs] == request["input_sha256"], "Frozen input content differs")
    pixels, descriptors, terms = xml_contract(inputs[0], inputs[1], request)
    intensity_integer = FORMATS[descriptors[0]["intensity"]["precision"]][0].startswith("int")
    spectra_schema = pa.schema([("pixel_id", pa.int64()), ("peak_id", pa.int64()), ("mz", arrow_type(descriptors[0]["mz"]["precision"])), ("intensity", arrow_type(descriptors[0]["intensity"]["precision"]))])
    pixel_rows, window_rows, summaries = [], [], [[] for window in request["windows"]]
    original_xml, original_binary = folder / NAMES[7], folder / NAMES[8]
    shutil.copyfile(inputs[0], original_xml); shutil.copyfile(inputs[1], original_binary)
    reference_eligible = all(not value["zlib"] and value["precision"] != "MS:1000520" for row in descriptors for value in row.values())
    parser = ImzMLParser(str(original_xml)) if reference_eligible else None
    try:
        if parser is not None: require([tuple(row[key] for key in ["x", "y", "z"]) for row in pixels] == parser.coordinates, "Official parser coordinate disagreement")
        with inputs[1].open("rb") as binary, pq.ParquetWriter(folder / NAMES[2], spectra_schema) as writer:
            for pixel_id, (pixel, arrays) in enumerate(zip(pixels, descriptors)):
                mz, intensity = decode(binary, arrays["mz"]), decode(binary, arrays["intensity"])
                masses, values = mz.tolist(), intensity.tolist()
                require(all(math.isfinite(value) and value >= 0 for value in masses), "Nonfinite/negative m/z signal")
                require(all(math.isfinite(value) for value in values), "Nonfinite spectral signal")
                if parser is not None:
                    reference_mass, reference_intensity = parser.getspectrum(pixel_id)
                    require(np.array_equal(mz, reference_mass) and np.array_equal(intensity, reference_intensity), "Official parser full spectrum disagreement")
                tic, tic_exact = signal(values, intensity_integer)
                pixel_rows.append(dict(pixel, pixel_id=pixel_id, n_peaks=len(masses), tic=tic, tic_exact_integer=tic_exact, **request["specimen_identity"]))
                table = pa.Table.from_arrays([pa.array([pixel_id] * len(masses), pa.int64()), pa.array(list(range(len(masses))), pa.int64()), pa.array(masses, spectra_schema.field("mz").type), pa.array(values, spectra_schema.field("intensity").type)], schema=spectra_schema)
                writer.write_table(table)
                for window_id, window in enumerate(request["windows"]):
                    selected = [value for mass, value in zip(masses, values) if window["lo"] <= mass <= window["hi"]]
                    total, exact = signal(selected, intensity_integer)
                    window_rows.append({"pixel_id": pixel_id, "window_id": window_id, "label": window["label"], "intensity": total, "exact_integer": exact, "detected": int(exact) > 0 if exact is not None else total > 0})
                    summaries[window_id].append((total, exact))
    finally:
        if parser is not None: parser.__exit__(None, None, None)
    aggregate = []
    for window_id, (window, samples) in enumerate(zip(request["windows"], summaries)):
        values = [value[0] for value in samples]
        numerator = sum(int(value[1]) for value in samples) if intensity_integer else None
        mean = float(numerator / len(pixels)) if numerator is not None else math.fsum(value / len(pixels) for value in values)
        require(math.isfinite(mean), "Nonfinite all-pixel window mean")
        maximum = max(int(value[1]) for value in samples) if intensity_integer else max(values)
        aggregate.append(dict(window, window_id=window_id, mean_intensity=mean, max_intensity=float(maximum), pixels_detected=sum(int(value[1]) > 0 if intensity_integer else value[0] > 0 for value in samples), pixels_total=len(pixels), exact_integer_numerator=str(numerator) if numerator is not None else None, exact_integer_maximum=str(maximum) if intensity_integer else None))
    pixel_schema = pa.schema([(key, pa.string() if key in ["spectrum_id", "z_origin", "tic_exact_integer", "donor_id", "organ", "slice_id"] else pa.float64() if key == "tic" else pa.int64()) for key in ["spectrum_id", "spectrum_index", "x", "y", "z", "z_origin", "pixel_id", "n_peaks", "tic", "tic_exact_integer", "donor_id", "organ", "slice_id"]])
    window_schema = pa.schema([(key, pa.string() if key in ["label", "exact_integer_numerator", "exact_integer_maximum"] else pa.float64() if key in ["lo", "hi", "mean_intensity", "max_intensity"] else pa.int64()) for key in ["label", "lo", "hi", "window_id", "mean_intensity", "max_intensity", "pixels_detected", "pixels_total", "exact_integer_numerator", "exact_integer_maximum"]])
    pair_schema = pa.schema([("pixel_id", pa.int64()), ("window_id", pa.int64()), ("label", pa.string()), ("intensity", pa.float64()), ("exact_integer", pa.string()), ("detected", pa.bool_())])
    for rows, schema, name in [(pixel_rows, pixel_schema, NAMES[0]), (aggregate, window_schema, NAMES[1]), (window_rows, pair_schema, NAMES[3])]: pq.write_table(pa.Table.from_pylist(rows, schema=schema), folder / name)
    require([digest(filename) for filename in inputs] == request["input_sha256"], "Source changed during ingestion")
    (folder / NAMES[6]).write_text("Complete imzML signals retained; UUID/checksums verified; pixels=" + str(len(pixels)) + "; pyimzML_full_array_parity=" + str(reference_eligible) + "; technical only\n")
    return {"pixels": len(pixels), "peaks": sum(row["n_peaks"] for row in pixel_rows), "windows": len(aggregate), "official_pyimzml_full_spectrum_parity": reference_eligible, "format_extension_not_upstream_parser_parity": not reference_eligible, "uuid": request["expected_uuid"], "declared_checksums_verified": {key: value for key, value in terms.items() if key in ["IMS:1000090", "IMS:1000091"]}}


def save_json(filename, value):
    filename.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def ledger(filename, test_id, status):
    with filename.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["test_id", "status", "scientific_release"])
        writer.writerow([test_id or "UNKNOWN_UNRECOVERABLE_ID", status, "NOT_GRANTED"])


def main():
    outputs = [Path(os.environ.get("AUTONOMICS_OUTPUT" + str(position), "/work/" + name)) for position, name in enumerate(NAMES)]
    audit = {"status": "BLOCKED", "test_id": None, "G0_granted": False, "statistical_official_layer": "NOT_APPLICABLE", "resident_daemon_certified": False}
    temporary, published, safe = None, [], False
    try:
        parent = outputs[0].parent
        require(parent.is_dir() and not parent.is_symlink() and len(set(outputs)) == len(outputs) and all(filename.is_absolute() and filename.parent == parent and filename.name == name and not filename.exists() and not filename.is_symlink() for filename, name in zip(outputs, NAMES)), "Unsafe or preexisting output paths")
        safe = True
        inputs = [Path(os.environ["AUTONOMICS_INPUT" + str(position)]) for position in range(3)]
        raw = inputs[2].read_text()
        audit["test_id"] = recover_test_id(raw)
        request = load_request(inputs[2]); validate(request)
        temporary = Path(tempfile.mkdtemp(prefix="imzml-publication-", dir=parent))
        details = calculate(inputs[:2], request, temporary)
        ledger(temporary / NAMES[5], request["test_id"], "TECHNICAL_PASS_NOT_SCIENTIFIC")
        audit.update(details, status="TECHNICAL_PASS_NOT_SCIENTIFIC", request=request, input_sha256=[digest(filename) for filename in inputs], output_sha256={str(position): digest(temporary / name) for position, name in enumerate(NAMES) if position != 4})
        save_json(temporary / NAMES[4], audit)
        for position, name in enumerate(NAMES):
            (temporary / name).replace(outputs[position]); published.append(outputs[position])
    except Exception as error:
        audit.update(status="BLOCKED", error=str(error)); audit.pop("output_sha256", None)
        if safe:
            for filename in published: filename.unlink()
            save_json(outputs[4], audit)
            ledger(outputs[5], audit["test_id"], "BLOCKED")
            outputs[6].write_text(str(error) + "\n")
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if temporary is not None: shutil.rmtree(temporary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
