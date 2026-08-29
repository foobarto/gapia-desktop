# Security Policy

Gapia Desktop controls USB hardware and the active GNOME display layout. Bugs
in these areas can affect device access, screen privacy, or session usability
and should be reported carefully.

## Supported versions

Until the first stable release, security fixes target the default branch and
the newest published prerelease. Older snapshots are not maintained.

## Reporting a vulnerability

Use GitHub's **Security** tab and select **Report a vulnerability** to open a
private security advisory. Do not include exploit details, sensitive logs, or
private device information in a public issue.

If private reporting is unavailable, email `bartosz@foobarto.me` with
`[gapia-security]` in the subject. PGP is strongly preferred for sensitive
material; the public key and fingerprint are listed in the
[account-wide security policy](https://github.com/foobarto/.github/blob/main/SECURITY.md),
which also contains the general rules of engagement and safe-harbor statement.

Include, when relevant:

- affected commit or release;
- hardware model, firmware, USB ID, GNOME version, and OS version;
- impact and the conditions required to reproduce it;
- minimal reproduction steps or a proof of concept;
- whether the issue involves udev permissions, SDK calls, display policy,
  layout snapshots, or the GNOME extension; and
- any suggested mitigation.

No fixed response or resolution deadline is promised. Maintainers will assess
the report, limit unnecessary disclosure, and coordinate a fix and publication
when the issue is within this project's control.

Report vulnerabilities in VITURE firmware or the separately supplied SDK to
VITURE. Report GNOME Shell or Mutter vulnerabilities to the GNOME project. If
the vulnerability is caused by how Gapia Desktop integrates with either one,
report it here first.

## Disclosure

Please allow reasonable time for triage and remediation before public
disclosure. Security advisories should credit reporters who request credit and
avoid publishing personal information or licensed vendor material.
