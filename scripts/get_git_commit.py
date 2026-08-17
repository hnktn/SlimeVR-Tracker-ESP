import datetime
import subprocess
import os

revision = ""

env_rev = os.environ.get("GIT_REV")
if not env_rev is None and env_rev != "":
    revision = env_rev
else:
    try:
        revision = (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
            .strip()
            .decode("utf-8")
        )
    except Exception:
        revision = "NOT_GIT"

# Version inherited from the nearest reachable tag, so that git tags stay the
# single source of truth. Yields a bare "0.7.3" when HEAD is exactly a tag and
# the tree is clean, "0.7.3-9-g2539157" further down the branch, and a trailing
# "-dirty" when the build includes uncommitted changes. Matches lightweight tags
# too, and is empty on a tagless clone such as a shallow CI checkout.
tag = ""
try:
	tag = subprocess.check_output(
		[
			"git",
			"--no-pager",
			"describe",
			"--tags",
			"--dirty",
			"--abbrev=7",
			"--match",
			"v*",
		],
		stderr=subprocess.DEVNULL,
	).strip().decode("utf-8")
	if tag.startswith("v"):
		tag = tag[1:]
except Exception:
	tag = ""

branch = ""
try:
	branch = (
		subprocess.check_output(["git", "symbolic-ref", "--short", "-q", "HEAD"])
			.strip()
			.decode("utf-8")
	)
except Exception:
	branch = ""

# Build date, day granularity so that a rebuild is only forced once per day.
# Override with BUILD_DATE, or with SOURCE_DATE_EPOCH for reproducible builds.
buildDate = os.environ.get("BUILD_DATE", "")
if buildDate == "":
	sourceDateEpoch = os.environ.get("SOURCE_DATE_EPOCH", "")
	if sourceDateEpoch != "":
		buildDate = datetime.datetime.fromtimestamp(
			int(sourceDateEpoch), datetime.timezone.utc
		).strftime("%Y%m%d")
	else:
		buildDate = datetime.date.today().strftime("%Y%m%d")

# The UDP handshake has no field for a build date, only a single version string,
# so the date is appended as SemVer build metadata to make it visible in the
# SlimeVR Server. An explicit FIRMWARE_VERSION is passed through untouched.
fwVersion = os.environ.get("FIRMWARE_VERSION")
if fwVersion is not None and fwVersion != "":
	version = fwVersion
elif tag != "":
	version = f"{tag}+{buildDate}"
elif branch != "":
	version = f"{branch}+{buildDate}"
else:
	version = f"git-{revision}+{buildDate}"

output = f"-DGIT_REV='\"{revision}\"'"
output += f" -DBUILD_DATE='\"{buildDate}\"'"
output += f" -DFIRMWARE_VERSION='\"{version}\"'"

print(output)
