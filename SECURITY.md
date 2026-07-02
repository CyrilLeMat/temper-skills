# Security policy

Report vulnerabilities privately via
[GitHub security advisories](https://github.com/CyrilLeMat/temper-skills/security/advisories/new)
— please don't open a public issue for anything exploitable.

Scope worth knowing: `temper-skills` executes **generated Python trees** with
`exec` when validating (`validate`, behavior-lock tests). Only run trees and
validation datasets you have reviewed — treat a `.py` tree from an untrusted
source like any other untrusted code.

Supported: the latest released version.
