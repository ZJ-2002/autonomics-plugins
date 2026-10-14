import copy
import unittest

from tools import publish_verified_ldsc_image as publisher


class AuthorImagePublicationTests(unittest.TestCase):
    def test_only_existing_exact_author_configuration_and_bounded_real_blobs_are_admitted(self):
        value = dict(schemaVersion=2, config=dict(digest=publisher.CONFIG, size=100),
                     layers=[dict(digest="sha256:"+"a"*64, size=1234)])
        publisher.check_manifest(value)
        for mutation in ["configuration", "empty", "invalid-size", "invalid-digest", "too-many"]:
            changed = copy.deepcopy(value)
            if mutation == "configuration": changed["config"]["digest"] = "sha256:"+"0"*64
            elif mutation == "empty": changed["layers"] = []
            elif mutation == "invalid-size": changed["layers"][0]["size"] = True
            elif mutation == "invalid-digest": changed["layers"][0]["digest"] = "mutable:latest"
            else: changed["layers"] *= 51
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                publisher.check_manifest(changed)

    def test_publication_cannot_rename_the_broken_runtime_as_the_author_image(self):
        self.assertNotEqual(publisher.SOURCE.split("@")[1], publisher.OLD_PUBLIC_DIGEST)
        self.assertEqual(publisher.REPOSITORY, "zj-2002/ldsc")
        self.assertEqual(publisher.TAG, "pristine-official-6c673952")
        self.assertIn("application/vnd.oci.image.manifest.v1+json", publisher.MEDIA)
        self.assertIn("application/vnd.docker.distribution.manifest.v2+json", publisher.MEDIA)


if __name__ == "__main__":
    unittest.main()
