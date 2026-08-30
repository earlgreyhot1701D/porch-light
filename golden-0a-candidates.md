# Golden set 0a — six candidate items

**Source document, all six:** City Council, Tuesday August 25, 2026
`https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08252026-3685`
`body_id: city_council` · `meeting_date: 2026-02-... → 2026-08-25` · document id 3685

**rewrite_provenance:** `AI drafted, human approved` — the twelve rewrites below were
drafted by Claude from the verbatim source text and reviewed line by line by Shara Cordero
before the golden set was built. Corrections made during that review are the ground truth;
the drafts are not. `spanish_reviewer` carries the same qualifier plus `unverified`.

**adversarial convention:** an adversarial item breaks exactly one language. The other
language of that same item is a correct rewrite and must PASS every check. `adversarial_language`
records which one is broken. Two broken rewrites, ten correct ones.

Open that PDF once and work down the list. For each item you need three things:

1. **Verbatim text** copied from the PDF for that item, with its page number
2. **A plain-English rewrite** you'd be happy for a neighbor to read
3. **A Spanish rewrite** (§8 fallback applies: if no fluent reviewer, write it yourself and mark `spanish_reviewer` as unverified)

---

## The six, and why each one is here

### 1. Consent item 1 — Approval of City Council minutes, July 7 and 14, 2026
**Exercises:** the floor. A trivially simple item.
**Why it matters:** if the verifier rejects a good rewrite of *this*, the verifier is broken, not the model. This is the calibration canary.
**Watch for:** two dates in one item. Both must normalize and survive Spanish.

**Item number:** 1
**Page:** 3
**Verbatim text:** (copied exactly from the PDF text layer; `û` is the PDF's rendering of an em/en-dash — left as extracted, not corrected)
> 1. City Council Minutes û Regular Meetings held on July 7, 2026 and July 14, 2026
>
> Staff: Michael MacDonald, City Clerk
>
> RECOMMENDATION
>
> Approve City Council Minutes for Regular Meetings held on July 7, 2026 and July 14, 2026.

**Plain-English rewrite:** The City Council will vote on whether to approve the written record of its own regular meetings held on July 7, 2026 and July 14, 2026. City Clerk Michael MacDonald is bringing it forward.
**Spanish rewrite:** El Concejo votará si aprueba el acta escrita de sus reuniones regulares del 7 de julio de 2026 y del 14 de julio de 2026. Lo presenta Michael MacDonald, City Clerk.
**Adversarial:** no

### 2. Consent item 2 — Ordinance allowing banking and financial services drive-through uses on Victoria Avenue
**Exercises:** a street name, the raw-compare case.
**Why it matters:** "Victoria Avenue" must appear untranslated in the Spanish rewrite. If it becomes "Avenida Victoria," check 6 must reject it, because a reader going to look for the street needs the name the city uses.
**Watch for:** whether your natural Spanish wants to translate it. That instinct is the bug the check exists to catch.

**Item number:** 2
**Page:** 3
**Verbatim text:** (copied exactly; `û` = dash, `ô`/`ö` = the PDF's curly double-quotes — left as extracted, not corrected)
> 2. Ordinance for Second Reading û An Ordinance to Amend Municipal Code for Victoria Avenue Corridor Plan and Development Code Amendments - Banking and Financial Services Drive-Through Uses
>
> Staff: Michael MacDonald, City Clerk
>
> RECOMMENDATION
>
> Waive the second reading in full and adopt of an Ordinance amending the Victoria Avenue Corridor Development Code (Chapter 24.600) Ordinance titled:
>
> ôAN ORDINANCE OF THE CITY COUNCIL OF THE CITY OF SAN BUENAVENTURA, CALIFORNIA, AMENDING CHAPTER 24.600, ôVICTORIA AVENUE CORRIDOR DEVELOPMENT CODE,ö TO ALLOW BANKING AND FINANCIAL SERVICES USES TO UTILIZE EXISTING LEGALLY ESTABLISHED DRIVE -THROUGH FACILITI ES AS A PERMITTED USEö

**Plain-English rewrite:** The City Council will take a final vote on a rule change for the Victoria Avenue Corridor. The change would let banking and financial services businesses use drive-through facilities that are already legally established on the corridor. It amends Chapter 24.600, the Victoria Avenue Corridor Development Code. City Clerk Michael MacDonald is bringing it forward.
**Spanish rewrite (DELIBERATELY BROKEN):** El Concejo dará el voto final a un cambio de reglamento para el corredor de la Avenida Victoria. El cambio permitiría que los negocios de servicios bancarios y financieros usen instalaciones de drive-through que ya están legalmente establecidas en el corredor. Modifica el Capítulo 24.600, el Código de Desarrollo del Corredor de la Avenida Victoria. Lo presenta Michael MacDonald, City Clerk.
**Adversarial:** yes
**adversarial_language:** es (the English rewrite is correct and must PASS)
**adversarial_reason:** Every instance of the street name "Victoria Avenue" is translated to "Avenida Victoria," including inside the name of the development code. A resident looking for the street, or for the code by name, would not find it. Check 6 must reject this rewrite.

### 3. Consent item 3 — Ordinance permitting general retail up to 140,000 SF in the T5.3 Zone
**Exercises:** government jargon plus a large number.
**Why it matters:** "T5.3 Zone" is meaningless to a resident, so this is where plain-language rewriting earns its keep. And 140,000 must survive normalization in both languages.
**Watch for:** the temptation to explain what T5.3 means using knowledge not in the item. That is a new entity and check 3 should catch it. If your correct rewrite trips check 3 here, that is a real calibration finding.

**Item number:** 3
**Page:** 4
**Verbatim text:** (copied exactly; `û` = dash, `ô`/`ö` = curly double-quotes — left as extracted. Note the title says "BETWEEN 100,000 AND 140,000 SQUARE FEET", so TWO numbers appear.)
> 3. Ordinance for Second Reading û Ordinance to Amend Municipal Code for Victoria Avenue Corridor Plan and Development Code to allow General Retail Uses up to 140,000 SF as a Permitted use in the T5.3 Zone
>
> Staff: Michael MacDonald, City Clerk
>
> RECOMMENDATION
>
> Waive the second reading in full and adopt an Ordinance amending the Victoria Avenue Corridor Development Code (Chapter 24.600) Ordinance titled:
>
> ôAN ORDINANCE OF THE CITY COUNCIL OF THE CITY OF SAN BUENAVENTURA, CALIFORNIA, AMENDING CHAPTER 24.600, ôVICTORIA AVENUE CORRIDOR DEVELOPMENT CODE,ö SECTION 24.600.180, ôLAND USE TABLE,ö TO ALLOW GENERAL RETAIL USES BETWEEN 100,000 AND 140,000 SQUARE FEET WITHIN THE URBAN CENTER ZONE (T5.3)ö

**Plain-English rewrite:** The City Council will take a final vote on a rule change for the Victoria Avenue Corridor. It would allow general retail uses between 100,000 and 140,000 square feet as a permitted use in the Urban Center Zone (T5.3). The change amends the land use table, Section 24.600.180, of Chapter 24.600, the Victoria Avenue Corridor Development Code. City Clerk Michael MacDonald is bringing it forward.
**Spanish rewrite:** El Concejo dará el voto final a un cambio de reglamento para el corredor de Victoria Avenue. Permitiría comercios de venta al público de entre 100.000 y 140.000 pies cuadrados como uso permitido en la Urban Center Zone (T5.3). El cambio modifica la tabla de usos de suelo, Sección 24.600.180, del Capítulo 24.600, el Victoria Avenue Corridor Development Code. Lo presenta Michael MacDonald, City Clerk.
**Adversarial:** no

### 4. Consent item 6 — First Amendment to the agreement with Cognizant Worldwide Limited, extended through September 4, 2027, $145,800
**Exercises:** a date and a dollar amount in the same item, plus a company name.
**Why it matters:** the densest normalization case. `September 4, 2027` and `4 de septiembre de 2027` must normalize equal. `$145,800` and `$145.800` (Spanish separator convention) must too. "Cognizant Worldwide Limited" compares raw.
**Watch for:** the number separator. Spanish convention uses a period where English uses a comma.

**Item number:** 6
**Page:** 5
**Verbatim text:** (copied exactly. Note the item contains THREE dates — Sept 5 2024, Sept 4 2027, Aug 31 2027 — and TWO amounts — $145,800 and $590,130. All are in source.)
> 6. First Amendment to Master Services Agreement and Statement of Work 2 with Cognizant Worldwide Limited
>
> Staff: Mike Shaffer, Chief Technology Officer
>
> RECOMMENDATION
>
> a. Authorize the City Manager, or designee, to execute the First Amendment to the Master Services Agreement with Cognizant Worldwide Limited, dated September 5, 2024, extending the term of the Agreement to September 4, 2027.
>
> b. Authorize the City Manager, or designee, to execute Statement of Work 2 with Cognizant Worldwide Limited in the amount of $145,800 through August 31, 2027, increasing the total not-to-exceed Agreement amount to $590,130.

**Plain-English rewrite (DELIBERATELY BROKEN):** The City Council will vote on extending the city's contract with Cognizant Worldwide Limited. The original agreement is dated September 5, 2024, and the extension would run the term through September 4, 2027. A second statement of work would add $145,900 through August 31, 2027, raising the total not-to-exceed amount of the agreement to $590,130. Chief Technology Officer Mike Shaffer is bringing it forward.
**Spanish rewrite:** El Concejo votará si extiende el contrato de la ciudad con Cognizant Worldwide Limited. El acuerdo original tiene fecha del 5 de septiembre de 2024 y la extensión llevaría el plazo hasta el 4 de septiembre de 2027. Un segundo statement of work agregaría $145.800 hasta el 31 de agosto de 2027, elevando el monto máximo total del acuerdo a $590.130. Lo presenta Mike Shaffer, Chief Technology Officer.
**Adversarial:** yes
**adversarial_language:** en (the Spanish rewrite is correct and must PASS)
**adversarial_reason:** The dollar amount $145,800 is stated as $145,900 in the English rewrite. Every other entity is correct. Check 2 must reject this rewrite on the amount alone.

### 5. Consent item 8 — Fourth Amendment to the crossing guard reimbursement agreement with the school district, $117,619
**Exercises:** money, plus something a person actually cares about.
**Why it matters:** this is the item a parent would want to know about, so it is good calibration *and* good demo material. A rewrite that makes this legible is the product working.
**Watch for:** "Fourth Amendment" is an ordinal in a contract name, not a constitutional reference. Interesting normalizer edge.

**Item number:** 8
**Page:** 6
**Verbatim text:** (copied exactly; `Jun e` and `2022 -053` spacing is as the PDF text layer produced it — not corrected. Two amounts: $117,619 and $521,679; one date: June 30, 2027.)
> 8. Fourth Amendment to Reimbursement Agreement 2022 -053 Between the Ventura Unified School District and the City of Ventura Regarding Crossing Guards for Fiscal Year 2027
>
> Staff: Charles W. Ebeling, Public Works Director
>
> RECOMMENDATION
>
> Authorize the City Manager, or designee, to execute the Fourth Amendment to Reimbursement Agreement 2022 -053 with the Ventura Unified School District allowing for additional reimbursement for crossing guard services through the end of Fiscal Year 2027 (Jun e 30, 2027) in the amount of $117,619 for a total Agreement amount not to exceed $521,679.

**Plain-English rewrite:** The City Council will vote on paying the Ventura Unified School District $117,619 more for crossing guard services through the end of Fiscal Year 2027, which ends June 30, 2027. This is the fourth amendment to Reimbursement Agreement 2022-053, and it would bring the total agreement amount to no more than $521,679. Public Works Director Charles W. Ebeling is bringing it forward.
**Spanish rewrite:** El Concejo votará si le paga al Ventura Unified School District $117.619 adicionales por el servicio de guardias de cruce escolar hasta el final del año fiscal 2027, que termina el 30 de junio de 2027. Es la cuarta modificación al Reimbursement Agreement 2022-053 y elevaría el monto total del acuerdo a un máximo de $521.679. Lo presenta Charles W. Ebeling, Public Works Director.
**Adversarial:** no

### 6. Formal item 10 — City Hall East Boiler Replacement Project, three options, Option A at $564,074
**Exercises:** the hard case. A genuine decision with alternatives.
**Why it matters:** the Council has three choices (gas boilers now, gas with a later heat-pump evaluation, or delay until heat-pump funding exists). A summary saying "the Council will replace the boilers" is **wrong**, because delay is on the table. This is the exact line between summarizing and taking a position, and it is where §4b lives.
**Watch for:** your own rewrite. If it implies an outcome, the model will too, and you will have learned the most important thing in this set.

**Item number:** 10
**Page:** 6-7 (SPANS TWO PAGES: the recommendation and Option A are on p6; Options B and C continue on p7)
**Verbatim text:** (copied exactly; `û` = dash. `$564,074` appears in both Option A and Option B. Project code `FA19-1149`/`FA19 -1149`/`FA19 - 1149` spacing varies as the text layer produced it — not corrected.)
> 10. City Hall East Boiler Replacement Project (FA19 -1149) Alternatives Analysis
>
> Staff: Charles W. Ebeling, Public Works Director
>
> RECOMMENDATION
>
> Select one of the following three options pertaining to the City Hall East boiler replacement project:
>
> a. Option A û Approve Natural Gas Boilers (estimated $564,074) and advertise bids for construction, or
>
> b. Option B û Approve Natural Gas Boilers (estimated $564,074), where staff would advertise bids for construction (FA19-1149), and evaluate a heat pump system when the City Hall East chiller units are due for replacement with replacement of the natural gas boilers in Option A, or
>
> c. Option C û Delay the replacement of the natural gas boilers (FA19 - 1149) with a heat pump system until funding is available within an indeterminate time.

**Plain-English rewrite:** The City Council has three options in front of it for the boilers at City Hall East (project FA19-1149), and it will choose one. Option A: approve natural gas boilers at an estimated $564,074 and advertise bids for construction. Option B: approve natural gas boilers at an estimated $564,074, advertise bids for construction, and evaluate a heat pump system later, when the City Hall East chiller units are due for replacement. Option C: delay replacing the natural gas boilers with a heat pump system until funding is available, with no set date. Public Works Director Charles W. Ebeling is bringing it forward. No option has been selected yet.
**Spanish rewrite:** El Concejo tiene tres opciones para las calderas de City Hall East (proyecto FA19-1149) y elegirá una. Opción A: aprobar calderas de gas natural por un estimado de $564.074 y sacar la construcción a licitación. Opción B: aprobar calderas de gas natural por un estimado de $564.074, sacar la construcción a licitación y evaluar un sistema de bomba de calor más adelante, cuando las unidades enfriadoras de City Hall East deban reemplazarse. Opción C: retrasar el reemplazo de las calderas de gas natural por un sistema de bomba de calor hasta que haya fondos disponibles, sin una fecha definida. Lo presenta Charles W. Ebeling, Public Works Director. Todavía no se ha elegido ninguna opción.
**Adversarial:** no

---

## Notes while you work

- **Copy verbatim.** The `source.text` field is ground truth for every check. Do not clean it up, do not fix its typos, do not expand its abbreviations.
- **Page numbers matter.** `page_range` is what the receipt points at. Record the actual page from the PDF.
- **Two of the six should be adversarial.** Mark `is_adversarial: true` and write a *deliberately broken* rewrite with the reason. Suggested: on item 4, change the dollar amount by one digit; on item 2, translate "Victoria Avenue" to "Avenida Victoria." Those two prove checks 2 and 6 actually bite.
- **If a correct rewrite of yours fails a check during calibration, the check is wrong.** That is the whole point of task 8. Record it and narrow the check.

## What happens next

Kiro runs calibration (task 8) against these six: reports which checks needed narrowing, derives the English and Spanish reading-level thresholds from the gap between your rewrites and their sources, and confirms the known-good rejection rate is zero. Only then does the model comparison run.

The other fourteen (task 0b) can come later; they gate model selection, not calibration.
