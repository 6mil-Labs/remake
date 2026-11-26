# OSHWA certification submission

`scripts/submit-oshwa.py` uses Python's standard library. No browser login or
password is needed, but authenticated API calls require a Bearer token.
Nothing is submitted unless you explicitly pass `--submit`. Signup is a
separate API request and does not certify or submit REMAKE.

## Obtain an API token

```sh
python3 scripts/submit-oshwa.py --signup \
  --first-name YOUR_FIRST_NAME --last-name YOUR_LAST_NAME --email YOUR_EMAIL
```

This calls `POST /users/signup` once and stores the returned token in
`~/.config/oshwa/token`, created with permissions `0600`. The token is not
printed and existing files are never overwritten. If you already registered,
use your existing API token; signup errors are not retried automatically.
The destination is reserved before contacting OSHWA. If signup succeeds but
writing the token fails, any removable partial file is deleted and the script
instructs you to contact OSHWA to recover access rather than signing up again.

Use `--token-file /private/path/token` to choose another location. Options and
submission accept the same flag. Otherwise they use `OSHWA_API_TOKEN` when set,
then the default token file. Never commit the token or include it in the payload.

```sh
python3 scripts/submit-oshwa.py --options
```

This makes a GET request for accepted country, licence and project-type values.
Use those exact values rather than guessing from SPDX identifiers. The hardware
is CERN-OHL-S-2.0; the firmware's actual licences and third-party notices must
be checked separately. This script is not a licensing/compliance audit.

## Prepare and review REMAKE's application

```sh
mkdir -p build
cp docs/oshwa-application.example.json build/oshwa-application.json
# Edit build/oshwa-application.json, then preview it without a network request:
python3 scripts/submit-oshwa.py build/oshwa-application.json
```

The example references the public **v0.3 prerelease**, whose release page links
the editable source archives and compatible Case v1.0 exports. Confirm that
v0.3 is the version you intend to certify; replace the version and documentation
link together if applying for another release. Personal information and licence
selections are intentionally blank. All declarations and legal agreements start
false: review the official terms and set each field yourself. Do not certify
v1.0 using documentation for an unpublished or different revision. Personal
application data belongs outside Git or in ignored `build/`.

Read the [requirements](https://certification.oshwa.org/requirements.html) and
[mark licence agreement](https://certification.oshwa.org/license-agreement.html).
The client checks essential fields, declaration types, explanations for negative
answers, and explicit agreement to all five named certification-mark terms. It
does not implement the entire server-side form validator or change your payload.
The API reports any additional field/choice errors.

The API has a certification-mark validation mismatch: its published form
validator checks an array's `length`, while OpenAPI documents an object with
five named agreements. With that object, an empty `explanationCertificationTerms`
can be rejected even when all five agreements are true. Keep the documented
object, and if you accept all five terms, explicitly enter
`"N/A: I agree to all five certification mark terms."` as the explanation.
The script checks for a nonempty explanation but never fills consent for you.

The [OpenAPI specification](https://certificationapi.oshwa.org/open-api-spec)
has inconsistencies: `noCommercialRestriction` is typed as a string but its
examples use a boolean; the template follows the boolean examples. It also
lists `certificationDate` as required without defining it. The client does not
invent a certification date or UID. Conditional `bindingParty` and `parentName`
fields should reflect the actual responsible party and applicable requirements.

## Submit explicitly

```sh
python3 scripts/submit-oshwa.py build/oshwa-application.json --submit
```

This sends one `POST /api/projects` request containing exactly your reviewed
JSON. It never follows redirects or automatically retries. On a timeout or
ambiguous response, check your application with OSHWA before retrying: repeating
a POST might create a duplicate. Signup has the same no-retry behavior.

An accepted submission is **not approval or permission to use the certification
mark**. Wait for OSHWA's approval/UID before adding it to the PCB. The script
does not publish releases, modify hardware, or add a logo.
