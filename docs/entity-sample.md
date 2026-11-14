# Entity resolution: 20 random companies checked by hand

The backtest needs to know which award notices were won by the same company.
Rules (`awards.resolve`, normaliser `awards.normalise_name`):

1. Normalise the winner name: lower case, strip accents and punctuation, strip legal forms
   at the end (GmbH, S.L.U., Sp. z o.o., s.r.o., Kft, …) and at the start (UAB, SIA, AS),
   and e-procurement artefacts (Swiss `DE_`/`FR_` tags, Irish `_12345` portal suffixes).
2. Same normalised name + same winner country = same company. For names of 4 characters or
   fewer ("OCI", "M.T."), the national ID must match as well.
3. Same national ID + same winner country + same **first word** of the name = same company.
   TED's winner IDs alone are unreliable: 1,697 of 16,048 IDs carried more than one name,
   often different firms (consortium partners, other tenderers' IDs).

**Sample:** `random.Random(20261114).sample` of the 2,555 companies with 4+ wins (the backtest
population) in `data/history.sqlite`. Each line: number of wins with that exact
(name, winner country, national ID).

**Result: 19 of 20 are clearly one firm; 1 is one corporate group with three legal entities
(#20). No unrelated firms merged.** The brief's limit is "more than 2 of 20 wrongly merged → tighten".

**How we got here (three review rounds, same seed):**
- Round 1 (before the rules above were final): 0 of 20 wrong merges, but two kinds of *missed*
  merges (one firm split in two): Swiss `DE_`/`FR_` language tags and Irish `_12345` suffixes.
  Fixed in the normaliser. A separate look at the top-15 list had already caught a wrong merge
  of three Lithuanian firms ("UAB Bitė Lietuva", "UAB CSC Telecom", "UAB Besmegeniai") through a
  shared ID and the shared first word "uab"; fixed by stripping prefix legal forms.
- Round 2: 2 of 20 doubtful, both very short names: "OCI" (France, 4 different IDs, one looking
  Portuguese) and "M.T. SpA" (Italy, 2 IDs). At the limit, not over it, but one cause, so
  rule 2 now needs a matching ID for names of 4 characters or fewer.
- Round 3 (this file, final rules): 1 of 20 questionable, below.

## 1. Entity 647: 61 wins, 5 variants

- 92 × `KING ICT d.o.o.` · HRV · ID 67001695549
- 21 × `KING ICT d.o.o.` · HRV · ID —
- 1 × `KING ICT Limited Liability Company for Business IT Services` · HRV · ID HR67001695549
- 1 × `KING ICT d.o.o.` · HRV · ID 88255578438
- 1 × `KING ICT d.o.o.` · HRV · ID HR67001695549

**Verdict:** ✅ One firm. The single row with ID 88255578438 is almost certainly a partner's ID listed by TED; the name matches exactly.

## 2. Entity 2581: 6 wins, 3 variants

- 3 × `EWORX YPIRESIES ILEKTRONIKOU EPICHEIREIN ANONYMOS ETAIREIA` · GRC · ID EL999982925
- 2 × `EWORX SA` · GRC · ID EL999982925
- 1 × `EWORX S.A` · GRC · ID 004244601000

**Verdict:** ✅ One firm: Greek long legal form and "SA" share ID EL999982925 and the first word.

## 3. Entity 11122: 12 wins, 8 variants

- 3 × `STORIO Sp. z o.o. sp. k` · POL · ID —
- 2 × `STORIO Spółka z ograniczoną odpowiedzialnością Spółka komandytowa` · POL · ID —
- 2 × `STORIO Spółka z ograniczoną odpowiedzialnością Spółka komandytowa` · POL · ID NIP6832087517
- 1 × `STORIO Sp. z o.o. Sp. k.` · POL · ID NIP8790169021
- 1 × `STORIO Sp. z o.o. sp. k` · POL · ID 5832790417
- 1 × `STORIO Sp. z o.o. sp. k` · POL · ID 6832087517
- 1 × `STORIO Spółka z ograniczoną odpowiedzialnością Spółka komandytowa` · POL · ID 6832087517
- 1 × `Storio Sp. z o.o. Sp.Komandytowa` · POL · ID 6832087517

**Verdict:** ✅ One firm (STORIO Sp. z o.o. Sp. k.); the odd NIPs are probably consortium partners' IDs, the name is identical.

## 4. Entity 13527: 5 wins, 4 variants

- 2 × `INNERGO SYSTEMS Sp. z o. o.` · POL · ID REGON141767212
- 1 × `INNERGO SYSTEMS SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ` · POL · ID PL9522064794
- 1 × `INNERGO SYSTEMS SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ` · POL · ID REGON141767212
- 1 × `INNERGO SYSTEMS Spółka z ograniczoną odpowiedzialnością` · POL · ID REGON000310232

**Verdict:** ✅ One firm; REGON and NIP variants of the same company.

## 5. Entity 8093: 4 wins, 2 variants

- 3 × `Spanish Point Technologies Ltd` · IRL · ID 403212
- 1 × `Spanish Point Technologies Ltd.` · IRL · ID 403212

**Verdict:** ✅ One firm.

## 6. Entity 8832: 4 wins, 4 variants

- 1 × `TACTICS` · BEL · ID 0471174233
- 1 × `Tactics` · BEL · ID —
- 1 × `Tactics BV` · BEL · ID BE0471174233
- 1 × `Tactics bv` · BEL · ID 0471174233

**Verdict:** ✅ One firm (Belgian ID 0471174233 with and without BE prefix).

## 7. Entity 1306: 19 wins, 7 variants

- 12 × `FourEnergy GmbH` · DEU · ID —
- 2 × `FourEnergy GmbH` · DEU · ID DE301265060
- 1 × `FourEnergy GmbH` · DEU · ID 33BE3459FEF74575A19AA9FA1E83F03F
- 1 × `FourEnergy GmbH` · DEU · ID C937ABA47E4D4AFA90834E1711ABBD3C
- 1 × `FourEnergy GmbH` · DEU · ID DE283446538
- 1 × `FourEnergy GmbH` · DEU · ID DE812816783
- 1 × `FourEnergy GmbH` · DEU · ID HRB55490

**Verdict:** ✅ One firm; several unrelated-looking IDs, but the name is distinctive and identical.

## 8. Entity 8451: 4 wins, 1 variants

- 4 × `IIT Development a. s.` · SVK · ID —

**Verdict:** ✅ One firm.

## 9. Entity 225: 10 wins, 7 variants

- 6 × `ATOS HOLDING IBERIA, S.L.` · ESP · ID B44676799
- 5 × `Atos Holding Iberia, S.L.` · ESP · ID B44676799
- 1 × `ATOS HOLDING IBERIA SL` · ESP · ID B44676799
- 1 × `Atos Holding Iberia, S.L.` · ESP · ID —
- 1 × `Atos Holding Iberia, S.L.` · ESP · ID A41132036
- 1 × `Atos Holding Iberia, S.L.` · ESP · ID A79153920
- 1 × `Atos Holding Iberia, S.L.` · ESP · ID B02761401

**Verdict:** ✅ One firm (Atos Holding Iberia); the A-/B- IDs on single rows are other Atos/partner entities' IDs, the name is identical.

## 10. Entity 6553: 6 wins, 6 variants

- 1 × `INFORMATICA MEDICO FARMACEUTICA SL` · ESP · ID —
- 1 × `INFORMATICA MEDICO FARMACEUTICA SL` · ESP · ID B96820154
- 1 × `INFORMÁTICA MÉDICO FARMACÉUTICA S.L.` · ESP · ID B96820154
- 1 × `INFORMÁTICA MÉDICO FARMACÉUTICA, S.L.` · ESP · ID B96820154
- 1 × `Informática Médico Farmacéutica, S.L.` · ESP · ID B66399452
- 1 × `Informática Médico Farmacéutica, S.L.` · ESP · ID B96820154

**Verdict:** ✅ One firm.

## 11. Entity 2540: 13 wins, 9 variants

- 4 × `IT arte Sp. z o.o.` · POL · ID 9512385491
- 2 × `IT. arte Sp. z o.o.` · POL · ID —
- 1 × `IT ARTE SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ` · POL · ID 9512385491
- 1 × `IT ARTE sp. z o.o` · POL · ID 9512385491
- 1 × `IT Arte Sp. z o.o.` · POL · ID 9512385491
- 1 × `IT arte Sp. z o.o.` · POL · ID —
- 1 × `IT arte Sp. z o.o.` · POL · ID REGON360205683
- 1 × `IT arte sp. z o.o.` · POL · ID —
- 1 × `It arte Sp.z o.o.` · POL · ID 9512385491

**Verdict:** ✅ One firm (IT arte, with and without the dot).

## 12. Entity 6359: 4 wins, 1 variants

- 4 × `Enovation Solutions_5766` · IRL · ID 328876

**Verdict:** ✅ One firm (the "_5766" portal suffix is stripped by the normaliser).

## 13. Entity 1579: 6 wins, 4 variants

- 3 × `DIaLOGIKa` · DEU · ID DE138187809
- 1 × `DIALOGIKA GESELLSCHAFT FUR ANGEWANDTE INFORMATIK MBH` · DEU · ID DE138187809
- 1 × `DIaLOGIKA Gesellschaft für angewandte Informatik mbH` · DEU · ID —
- 1 × `DIaLOGIKa GmbH` · DEU · ID DE138187809

**Verdict:** ✅ One firm: "DIaLOGIKa" and the long GmbH name share ID DE138187809 and the first word.

## 14. Entity 240: 11 wins, 5 variants

- 5 × `SOFTEAM` · FRA · ID —
- 4 × `SOFTEAM` · FRA · ID 49324189700096
- 1 × `SOFTEAM` · FRA · ID 49324189700120
- 1 × `SOFTEAM SAS` · FRA · ID —
- 1 × `SOFTEAM SAS` · FRA · ID 49324189700096

**Verdict:** ✅ One firm (two SIRET establishments of SOFTEAM).

## 15. Entity 6157: 8 wins, 6 variants

- 4 × `ATMOTERM S.A.` · POL · ID 7540339496
- 1 × `ATMOTERM SPÓŁKA AKCYJNA` · POL · ID REGON530600238NIP7540339496
- 1 × `ATMOTERM Spółka Akcyjna` · POL · ID 7540339496
- 1 × `Atmoterm S.A.` · POL · ID 530600238
- 1 × `Atmoterm S.A.` · POL · ID 7540339496
- 1 × `Atmoterm S.A.` · POL · ID 89992902826

**Verdict:** ✅ One firm (REGON/NIP variants).

## 16. Entity 17232: 5 wins, 2 variants

- 8 × `KONČAR - Digital d.o.o.` · HRV · ID 55191916939
- 2 × `KONČAR - Digital d.o.o.` · HRV · ID —

**Verdict:** ✅ One firm.

## 17. Entity 10439: 6 wins, 3 variants

- 3 × `Consileon Business Consultancy GmbH` · AUT · ID —
- 2 × `Consileon Business Consultancy GmbH` · AUT · ID FN305082A
- 1 × `Consileon Business Consultancy GmbH` · AUT · ID 9110017205358

**Verdict:** ✅ One firm (Firmenbuch and other Austrian ID).

## 18. Entity 5093: 6 wins, 6 variants

- 1 × `SmartSimple Software` · IRL · ID 332915
- 1 × `SmartSimple Software Ireland Limited` · IRL · ID —
- 1 × `SmartSimple Software Ireland Ltd` · IRL · ID 9649314V
- 1 × `Smartsimple Software Ireland Limited` · IRL · ID 332915
- 1 × `Smartsimple Software Ireland Limited` · IRL · ID 9649314V
- 1 × `Smartsimple Software Ireland Ltd.` · IRL · ID —

**Verdict:** ✅ One firm (SmartSimple Software Ireland).

## 19. Entity 5469: 4 wins, 1 variants

- 5 × `TECHED SAVJETODAVNE USLUGE d.o.o.` · HRV · ID 19130560524

**Verdict:** ✅ One firm.

## 20. Entity 3046: 4 wins, 3 variants

- 2 × `Nortal AG` · None · ID —
- 1 × `Nortal AS` · None · ID —
- 1 × `Nortal GmbH` · None · ID —

**Verdict:** ⚠️ **Questionable: one brand, three legal entities.** Nortal AG, Nortal AS (Estonia) and Nortal GmbH, all with no winner country in TED, so they share the "no country" name key after the legal form is stripped. Same corporate group and IT-services profile, so harmless for the backtest, but strictly not one firm. Counted as a wrong merge.
