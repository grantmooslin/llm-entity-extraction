# Experiment report — qwen3.7-flash_sorter_docclass_correspondence_v1_enron200_s42

Generated: 2026-08-30T01:42:22.738268+00:00

## Run metadata

- task: `correspondence_classification`
- prompt version: `sorter_docclass_correspondence_v1`
- model: `qwen/qwen3.7-flash`
- hf_repo: `Lucius-Morningstar/enron-correspondence-dedup`
- dataset size: `200`
- stratified / seed: `200 / 42`
- braintrust_logging: `True`
- git: `aaa9a55`
- ground truth: `expected + expected_subclass + sentiment_label + sentiment_score`

## Aggregate scorers

- rows: **200** (errors: 0)
- doc_type_accuracy: **1.0000**
- subclass_accuracy: **0.4650** (equiv 0.4650)
- exact_match (doc_type ∧ subclass): **0.4650**
- sentiment_label_accuracy: **0.6250**
- sentiment_score_ok (band 0.25): **0.7705**
- sentiment_score_mae: **0.1580**
- correspondence_exact (type ∧ subclass ∧ sentiment label): **0.3500**
- confidence: **0.8625**

## Tokens / cost

- prompt tokens: `1616703`
- completion tokens: `257563`
- total cost: `—`

## Per-subclass accuracy

| subclass | accuracy | support |
|----------|----------|---------|
| attorney_demand | 0.0000 | 3 |
| demand | 0.0000 | 25 |
| email | 0.7021 | 47 |
| letter | 0.4400 | 25 |
| meeting_request | 0.8000 | 25 |
| memo | 0.2400 | 25 |
| notice | 0.4400 | 25 |
| press_release | 0.4800 | 25 |

## Subclass confusion (expected \ predicted)

| expected \ predicted | attorney_demand | demand | email | letter | meeting_request | memo | notice | other | press_release |
|---|---|---|---|---|---|---|---|---|---|
| attorney_demand | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 1 | 0 |
| demand | 0 | 0 | 20 | 2 | 0 | 1 | 1 | 0 | 1 |
| email | 0 | 1 | 33 | 5 | 3 | 1 | 2 | 2 | 0 |
| letter | 0 | 0 | 2 | 11 | 5 | 0 | 4 | 3 | 0 |
| meeting_request | 0 | 0 | 3 | 0 | 20 | 0 | 0 | 2 | 0 |
| memo | 0 | 0 | 13 | 0 | 1 | 6 | 3 | 2 | 0 |
| notice | 0 | 0 | 8 | 0 | 1 | 0 | 11 | 5 | 0 |
| other | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| press_release | 0 | 0 | 9 | 0 | 1 | 0 | 1 | 2 | 12 |

## Per-sentiment-label accuracy

| sentiment_label | accuracy | support |
|-----------------|----------|---------|
| negative | 0.1071 | 28 |
| neutral | 0.8870 | 115 |
| positive | 0.3509 | 57 |

## Sentiment confusion (expected \ predicted)

| expected \ predicted | negative | neutral | positive | unknown |
|---|---|---|---|---|
| negative | 3 | 20 | 2 | 3 |
| neutral | 1 | 102 | 7 | 5 |
| positive | 1 | 27 | 20 | 9 |
| unknown | 0 | 0 | 0 | 0 |

## Failure insights

- n_failed: **130**
- mode_counts: `{'subclass_miss': 107, 'sentiment_miss': 23}`

## Misclassification ledger

_130 rows; showing 100._

| mode | filename | expected subclass | predicted subclass | expected sent. | predicted sent. | reasoning |
|------|----------|-------------------|--------------------|-----------------|-----------------|-----------|
| subclass_miss | sanders-r/px/19. | attorney_demand | email | neutral | neutral | The payload is a brief administrative message forwarding an attached draft for discussion at a pre-scheduled committee meeting. It lacks formal demand language, |
| subclass_miss | blair-l/inbox/88. | demand | email | neutral | neutral | The document is a brief, informal internal message from one colleague to another attaching a draft notice for review. It lacks formal headings, demands, or offi |
| subclass_miss | bass-e/deleted_items/252. | email | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=16064, total_tokens=18110, compl |
| subclass_miss | lay-k/all_documents/956. | letter | notice | neutral | neutral | The document functions as an official regulatory notice/reminder regarding SEC Form 4 filing obligations. It delivers factual administrative instructions and a  |
| subclass_miss | jones-t/deleted_items/12. | memo | notice | neutral | neutral | The document is explicitly titled 'Notice No. 01-417' and functions as an official exchange announcement to members regarding adjusted trading hours for New Yea |
| subclass_miss | dasovich-j/inbox/800. | press_release | email | neutral | neutral | The document is an internal corporate communication providing guidance on handling media inquiries related to SEC investigations and lawsuits. It features a sub |
| subclass_miss | lavorato-j/old_inbox/85. | email | letter | positive | positive | The payload is a customer-facing promotional invitation formatted with a formal salutation and closing ('Dear Morningstar.com Premium Member:' / 'Sincerely'), w |
| sentiment_miss | baughman-d/inbox/346. | email | email | neutral | positive | The document is a promotional HTML email blast from Sweepsclub.com advertising cash advances and reward points. It lacks formal legal demands, meeting requests, |
| subclass_miss | baughman-d/deleted_items/32. | email | letter | neutral | neutral | The document is a daily news wrap-up newsletter addressed to a subscriber ('Dear Don'), summarizing upcoming broadcast segments and listing commodity closing pr |
| subclass_miss | corman-s/inbox/archives/4. | email | memo | positive | positive | The document serves as an internal team briefing announcing a personnel appointment and role assignment, fitting the memo subclass per rule 45. The language is  |
| sentiment_miss | germany-c/_sent_mail/3. | email | email | positive | neutral | The document is an informal internal email thread between colleagues discussing invoice timing. It lacks formal headings, legal demands, or meeting requests, fi |
| sentiment_miss | germany-c/sent_items/707. | email | email | neutral | positive | The document is a brief transactional message acknowledging receipt of a fax and expressing thanks. It lacks the formal structure of a letter or the specific fu |
| subclass_miss | fischer-m/deleted_items/27. | email | notice | neutral | neutral | The document is an automated system notification reporting the payment status of an expense report. It functions as a system notice rather than a personal or bu |
| sentiment_miss | scott-s/deleted_items/448. | email | email | neutral | positive | The document is an internal club announcement updating members on the upcoming spring season, requesting volunteers, and offering running gear for sale. It func |
| subclass_miss | shively-h/_sent_mail/207. | email | meeting_request | neutral | neutral | The document is a calendar invitation for a recurring weekly status meeting, which directly matches the meeting_request subclass per rule 45. The content is pur |
| subclass_miss | lavorato-j/california/3. | email | meeting_request | negative | neutral | The document is an agenda for a scheduled call, which directly matches the meeting_request subclass per rule 45 (agenda-for-attendance). The content is purely a |
| sentiment_miss | germany-c/_sent_mail/80. | email | email | negative | neutral | The document is an informal internal email thread between colleagues discussing the execution of legal documents, addendums, and weekend plans. It lacks formal  |
| sentiment_miss | lewis-a/deleted_items/79. | email | email | neutral | positive | The document is a promotional customer newsletter/email from eBay featuring Valentine's Day gift suggestions and special offers. It functions as a commercial br |
| subclass_miss | ybarbo-p/inbox/150. | memo | email | positive | neutral | The document is an internal business email thread between colleagues discussing the validity and handling of a ship demurrage claim. It lacks formal demands, me |
| subclass_miss | kean-s/sent_items/230. | memo | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8662, total_tokens=10710, comple |
| subclass_miss | bass-e/all_documents/272. | memo | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8691, total_tokens=10739, comple |
| subclass_miss | hayslett-r/projects/lng__global_/1. | memo | email | positive | neutral | The document is an internal business message sharing a spreadsheet, delegating review tasks to colleagues, and outlining next steps. Its format (Subject header, |
| subclass_miss | motley-m/inbox/ene_portland/administrative/19. | memo | email | neutral | neutral | The document is a brief internal forwarding of a voicemail message to employees, functioning as a routine informational email. It lacks formal notice, demand, o |
| subclass_miss | hain-m/all_documents/897. | memo | email | neutral | neutral | The document consists entirely of a standard email confidentiality disclaimer and an attachment reference, lacking any substantive operational or communicative  |
| subclass_miss | jones-t/all_documents/5972. | memo | email | neutral | neutral | The document is an informal business communication requesting a specific corporate document (Memorandum of Association) to be faxed. It lacks formal memo or let |
| subclass_miss | mcconnell-m/all_documents/851. | memo | email | positive | positive | The document is an internal email thread containing a corporate charity fundraising announcement and a follow-up inquiry. It uses standard email headers and lac |
| subclass_miss | ermis-f/inbox/666. | memo | notice | neutral | neutral | The document is an official announcement to shippers regarding updated fuel factors and rate schedules effective on a specific date, explicitly labeled as a 'No |
| subclass_miss | sanders-r/all_documents/255. | memo | email | negative | neutral | The document is an informal internal update between colleagues regarding deposition progress and upcoming schedules. It does not meet the criteria for demands,  |
| subclass_miss | dickson-s/all_documents/132. | memo | email | neutral | neutral | The document is a brief, informal business update between colleagues regarding the distribution of a memo, fitting the residual 'email' subclass. The content is |
| subclass_miss | rogers-b/all_documents/440. | memo | email | neutral | positive | The payload is an informal internal email thread between colleagues coordinating a lunch, matching the email subclass per rule 45. The tone is upbeat and cooper |
| subclass_miss | nemec-g/all_documents/5291. | memo | email | neutral | neutral | The payload is an informal internal work instruction between colleagues regarding document comparison, approval routing, and drafting assistance. It lacks forma |
| subclass_miss | fossum-d/all_documents/588. | memo | email | neutral | neutral | The document is an internal company email thread addressing a technical messaging glitch, apologizing for confusion, and instructing recipients on next steps. I |
| subclass_miss | kean-s/all_documents/5045. | memo | email | positive | neutral | The document is an informal internal email thread between colleagues discussing a previously approved memo. The payload contains brief, routine acknowledgments  |
| subclass_miss | corman-s/all_documents/9. | memo | meeting_request | neutral | neutral | The payload is an email thread providing dial-in instructions and confirming dates/times for upcoming conference calls to review a proposal. Its primary functio |
| subclass_miss | shackleton-s/all_documents/8952. | memo | notice | neutral | neutral | The document is explicitly titled 'Notice No. 01-51' and functions as an official exchange announcement to NYMEX members regarding margin rate changes for speci |
| sentiment_miss | steffes-j/inbox/419. | memo | memo | positive | neutral | The document explicitly begins with a MEMORANDUM header and follows a standard TO/FROM/DATE/RE structure, functioning as an internal policy briefing and coordin |
| subclass_miss | dasovich-j/all_documents/8769. | memo | email | negative | positive | The document is an internal corporate email thread assigning follow-up tasks and drafting regulatory correspondence regarding Senate hearings. Its informal coll |
| subclass_miss | mann-k/_sent_mail/2750. | notice | email | positive | neutral | The document is an internal email thread between colleagues coordinating contract details and forwarding legal questions. It lacks formal notice, demand, or mem |
| subclass_miss | hyatt-k/projects/28. | notice | meeting_request | positive | neutral | The payload is an email thread whose primary purpose is to share technical pipeline pressure data and explicitly propose scheduling a follow-up meeting by reque |
| subclass_miss | dasovich-j/all_documents/4411. | notice | email | neutral | neutral | The document is an internal email forwarding a link to a regulatory draft decision and notice of written exceptions. It does not trigger any higher-priority cor |
| subclass_miss | dasovich-j/all_documents/10684. | notice | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=13156, total_tokens=15204, compl |
| subclass_miss | mann-k/_sent_mail/2184. | notice | email | neutral | neutral | Internal informal email thread between colleagues discussing proofreading a draft notice; matches the residual 'email' category per rule 45. The tone is routine |
| sentiment_miss | jones-t/all_documents/5967. | notice | notice | positive | neutral | The document is explicitly titled 'Notice No. 00-421' and functions as an official exchange announcement to members regarding temporary trading limit amendments |
| subclass_miss | germany-c/_sent_mail/1345. | notice | email | neutral | neutral | The document is an informal internal email thread between colleagues discussing a storage contract's expiration and assigning follow-up responsibility. It does  |
| subclass_miss | sager-e/deleted_items/42. | notice | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=8567, total_tokens=10613, comple |
| subclass_miss | lokay-m/all_documents/206. | notice | email | positive | neutral | The payload is an internal request for a summary of contract transport options following a staff meeting. It functions as a routine administrative email with a  |
| subclass_miss | platter-p/deleted_items/11. | notice | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8928, total_tokens=10976, comple |
| subclass_miss | haedicke-m/all_documents/5022. | notice | email | neutral | positive | The document is an internal business note forwarding regulatory background materials ahead of a scheduled conference call. It lacks formal memo headers, demands |
| subclass_miss | rapp-b/inbox/115. | notice | email | positive | neutral | The document is an internal email thread between colleagues (Frazier and Tracy Scott) providing routine instructions on processing employee transfers and organi |
| subclass_miss | kitchen-l/_americas/mexico/6. | notice | email | neutral | neutral | The document is an informational message clarifying contractual notification obligations under a Power Purchase Agreement. Its informal, explanatory tone and br |
| subclass_miss | hain-m/all_documents/250. | notice | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9153, total_tokens=11201, comple |
| subclass_miss | thomas-p/deleted_items/543. | notice | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=12435, total_tokens=14483, compl |
| subclass_miss | horton-s/all_documents/69. | letter | meeting_request | neutral | neutral | The payload distributes a draft agenda for an upcoming board meeting, which directly satisfies the meeting_request subclass criteria under rule 45. The tone is  |
| sentiment_miss | lay-k/all_documents/565. | letter | letter | positive | neutral | The document follows a formal business letter format with a salutation ('Dear Mr. Lay') and closing ('Yours faithfully'), serving as a routine follow-up and cla |
| sentiment_miss | mims-thurston-p/deleted_items/67. | letter | letter | neutral | positive | The payload functions as a customer welcome newsletter with a formal salutation and closing ('Dear Amazon Customer,' 'Sincerely,'), which maps to the 'letter' s |
| subclass_miss | kaminski-v/all_documents/9712. | letter | meeting_request | positive | positive | The payload's primary purpose is to propose and schedule a follow-up visit/meeting ('visit you in Houston to learn more about your operations'), which directly  |
| subclass_miss | campbell-l/inbox/344. | letter | notice | negative | neutral | The payload constitutes an official system update and announcement from NYISO to market participants regarding software release delays and new data postings, fi |
| subclass_miss | buy-r/inbox/438. | letter | meeting_request | negative | positive | The document is a formal invitation to speak at a conference, requesting a response at the recipient's earliest convenience. Its primary function is to invite p |
| subclass_miss | ruscitti-k/inbox/279. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=8703, total_tokens=10749, comple |
| subclass_miss | lay-k/all_documents/455. | letter | meeting_request | positive | positive | The payload is a business email whose primary function is to confirm attendance and acknowledge scheduling details for an upcoming executive meeting, which trig |
| subclass_miss | campbell-l/inbox/669. | letter | meeting_request | neutral | neutral | The document is an email notification whose primary purpose is to schedule and confirm attendance for a working group meeting, providing the date, time, physica |
| subclass_miss | shackleton-s/all_documents/8895. | letter | email | positive | neutral | The document is a business email requesting contact information and procedural guidance to initiate an ISDA Master Agreement negotiation. It lacks formal notice |
| subclass_miss | kaminski-v/all_documents/5939. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8718, total_tokens=10766, comple |
| subclass_miss | thomas-p/deleted_items/183. | letter | email | neutral | neutral | The document is an email forwarding presentation materials for a scheduled working group meeting. It lacks demands, scheduling requests, or formal notices, plac |
| subclass_miss | rogers-b/deleted_items/302. | letter | notice | negative | neutral | The payload is an official system announcement directed to market participants regarding a recent SCD operational problem and its resolution, which aligns with  |
| subclass_miss | smith-m/deleted_items/47. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9274, total_tokens=11322, comple |
| subclass_miss | lay-k/all_documents/240. | letter | notice | negative | neutral | The document functions as an official announcement to USIBC members regarding the cancellation of San Francisco events and the updated Washington D.C. schedule. |
| subclass_miss | kitchen-l/_americas/eol/2. | press_release | email | neutral | neutral | The document is an internal work message from one colleague to another sharing a project activity list and timeline. It does not contain demands, formal notices |
| subclass_miss | shapiro-r/broadband_services/42. | press_release | email | negative | neutral | The document is an informal internal business update between colleagues regarding legislative monitoring, regulatory filings, and coalition efforts. It lacks fo |
| subclass_miss | kitchen-l/sent_items/612. | press_release | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8888, total_tokens=10936, comple |
| subclass_miss | shankman-j/inbox/53. | press_release | email | neutral | neutral | The payload is an informal business message between colleagues sharing follow-up materials from a conference call, which fits the email subclass under rule 45.  |
| subclass_miss | kean-s/all_documents/6036. | press_release | email | neutral | neutral | Internal business email forwarding a draft press release for stakeholder review and approval. The content is factual and routine, requesting feedback without st |
| sentiment_miss | grigsby-m/all_documents/132. | press_release | press_release | positive | neutral | The document explicitly features 'NEWS RELEASE' and 'FOR IMMEDIATE RELEASE' headers, a dateline, and a media contact, which directly triggers the press_release  |
| subclass_miss | derrick-j/deleted_items/121. | press_release | meeting_request | neutral | neutral | The document is an internal communication whose primary purpose is to coordinate schedules and request attendance for an upcoming meeting ('Whalley wants you AS |
| subclass_miss | zipper-a/deleted_items/352. | press_release | email | neutral | neutral | The payload is an internal email thread where a colleague asks clarifying questions about a draft press release's strategic objectives. It functions as an infor |
| sentiment_miss | dasovich-j/all_documents/9891. | press_release | press_release | negative | neutral | The payload is a formal 'FOR IMMEDIATE RELEASE' statement from the Office of the Governor regarding a regulatory request to FERC for temporary wholesale power p |
| subclass_miss | dasovich-j/all_documents/201. | press_release | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=10267, total_tokens=12313, compl |
| subclass_miss | hain-m/all_documents/1318. | press_release | email | positive | neutral | The document is an internal business email forwarding draft legal agreements and requesting peer review. It lacks formal demands, meeting invitations, or offici |
| subclass_miss | hayslett-r/all_documents/470. | press_release | email | positive | positive | The payload consists of brief, informal internal messages between colleagues discussing a recent announcement and accounting change. It lacks formal business-le |
| sentiment_miss | tholt-j/deleted_items/219. | press_release | press_release | negative | neutral | The document explicitly features 'NEWS RELEASE' and 'FOR IMMEDIATE RELEASE' headers, a dedicated media contact line, and terminates with the standard '# # #' pr |
| sentiment_miss | dasovich-j/all_documents/2975. | press_release | press_release | positive | negative | The payload is explicitly formatted and titled as a press release ('Davis Press Release', transcript of remarks, ends with '# # #' and legislative analyst conta |
| subclass_miss | south-s/all_documents/26. | press_release | notice | neutral | neutral | The document is explicitly formatted as an operational notice from Kern River regarding IT/AOS capacity for May 2001, featuring standard notice fields (Notice T |
| subclass_miss | skilling-j/inbox/1228. | press_release | email | positive | positive | The document follows a standard email format with a subject line and informal business sign-off, fitting the email subclass under the correspondence cascade. Th |
| sentiment_miss | buy-r/deleted_items/89. | press_release | press_release | positive | neutral | The message explicitly forwards two attached press releases from Viking, triggering the press_release subclass under rule 45. The content is a routine corporate |
| subclass_miss | cash-m/all_documents/30. | demand | memo | negative | neutral | The document is an internal performance summary and work briefing from an employee to a supervisor detailing accomplishments across multiple practice areas. Thi |
| subclass_miss | taylor-m/all_documents/3517. | demand | email | negative | neutral | The document is an email thread between Enron personnel and outside counsel discussing proposed revisions to contract clauses (limitation of liability, indemnit |
| subclass_miss | lewis-a/deleted_items/442. | demand | email | positive | positive | The document contains a subject line, inline image placeholders, and direct calls-to-action ('Click here!'), which are characteristic of an email. Its primary f |
| subclass_miss | ring-r/eesirenewableenergy/13. | demand | email | positive | neutral | The document is an informal email thread between colleagues discussing meter quantities, invoicing instructions, and volume forecasts. It does not trigger the h |
| subclass_miss | campbell-l/all_documents/393. | demand | email | positive | neutral | Internal business email thread between colleagues coordinating environmental audit follow-ups and remediation responsibilities. Matches the residual 'email' sub |
| subclass_miss | mann-k/all_documents/3627. | demand | email | negative | neutral | Per explicit instruction, classified as correspondence. The text is a standalone contractual waiver clause regarding consequential damages lacking headers, salu |
| subclass_miss | sanders-r/deleted_items/472. | demand | email | positive | neutral | The document is an internal corporate email updating a colleague on a received arbitration notice and its potential impact on a pending merger. It follows the i |
| subclass_miss | germany-c/sent_items/636. | demand | email | negative | neutral | The document is an internal email thread discussing verification of an unpaid invoice and payment authorization. It lacks formal demand, notice, or memorandum s |
| subclass_miss | schoolcraft-d/inbox/junk/351. | demand | letter | positive | neutral | The document is a weekly industry newsletter ('RIGZONE Industry News') featuring market headlines, event listings, and advertisements. Per rule 45, a community  |
| subclass_miss | arnold-j/deleted_items/243. | demand | notice | neutral | neutral | The document is explicitly titled 'FINAL NOTICE' and functions as an official IT system announcement regarding a scheduled migration and outage, matching the 'n |
| subclass_miss | lavorato-j/deleted_items/300. | demand | email | negative | negative | The document is an internal email thread discussing billing, settlements, and reconciliation process delays. The payload consists of informal corporate messages |
| subclass_miss | shackleton-s/inbox/767. | demand | email | neutral | neutral | The document is an internal email thread between colleagues requesting contact information to determine a default rate. It lacks formal demand, meeting, or noti |
| subclass_miss | haedicke-m/all_documents/902. | demand | email | neutral | neutral | The document is an internal email thread forwarding scanned copies of guarantee demand letters and outlining the procedural timeline for serving subsequent noti |
| subclass_miss | shackleton-s/inbox/862. | demand | email | neutral | neutral | The document is an internal corporate email requesting a system check for a delinquent invoice before contacting the client. It follows standard email formattin |
| subclass_miss | blair-l/inbox/171. | demand | email | positive | neutral | The document is an internal email thread between colleagues updating each other on negotiation status and dispute resolution steps. It lacks formal demand, lega |
| subclass_miss | mann-k/sent_items/39. | demand | email | neutral | neutral | The payload is a brief, informal request between colleagues for specific documents ('notice of default and our response'), lacking formal headings or legal dema |
