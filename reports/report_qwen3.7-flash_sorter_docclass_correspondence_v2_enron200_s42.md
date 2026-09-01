# Experiment report — qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42

Generated: 2026-08-30T02:04:08.288096+00:00

## Run metadata

- task: `correspondence_classification`
- prompt version: `sorter_docclass_correspondence_v2`
- model: `qwen/qwen3.7-flash`
- hf_repo: `Lucius-Morningstar/enron-correspondence-dedup`
- dataset size: `200`
- stratified / seed: `200 / 42`
- braintrust_logging: `True`
- git: `de0323b`
- ground truth: `expected + expected_subclass + sentiment_label + sentiment_score`

## Aggregate scorers

- rows: **200** (errors: 0)
- doc_type_accuracy: **1.0000**
- subclass_accuracy: **0.4850** (equiv 0.4850)
- exact_match (doc_type ∧ subclass): **0.4850**
- sentiment_label_accuracy: **0.6100**
- sentiment_score_ok (band 0.25): **0.7821**
- sentiment_score_mae: **0.1581**
- correspondence_exact (type ∧ subclass ∧ sentiment label): **0.3850**
- confidence: **0.8455**

## Tokens / cost

- prompt tokens: `1649496`
- completion tokens: `254127`
- total cost: `—`

## Per-subclass accuracy

| subclass | accuracy | support |
|----------|----------|---------|
| attorney_demand | 0.3333 | 3 |
| demand | 0.1200 | 25 |
| email | 0.6596 | 47 |
| letter | 0.4000 | 25 |
| meeting_request | 0.8000 | 25 |
| memo | 0.2400 | 25 |
| notice | 0.4800 | 25 |
| press_release | 0.5600 | 25 |

## Subclass confusion (expected \ predicted)

| expected \ predicted | attorney_demand | demand | email | letter | meeting_request | memo | notice | other | press_release |
|---|---|---|---|---|---|---|---|---|---|
| attorney_demand | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 0 |
| demand | 0 | 3 | 12 | 2 | 0 | 1 | 0 | 6 | 1 |
| email | 0 | 0 | 31 | 8 | 3 | 0 | 2 | 3 | 0 |
| letter | 0 | 0 | 3 | 10 | 4 | 0 | 2 | 6 | 0 |
| meeting_request | 0 | 0 | 4 | 0 | 20 | 1 | 0 | 0 | 0 |
| memo | 0 | 0 | 12 | 0 | 2 | 6 | 3 | 2 | 0 |
| notice | 0 | 0 | 8 | 2 | 1 | 0 | 12 | 2 | 0 |
| other | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| press_release | 0 | 0 | 7 | 0 | 1 | 1 | 1 | 1 | 14 |

## Per-sentiment-label accuracy

| sentiment_label | accuracy | support |
|-----------------|----------|---------|
| negative | 0.1071 | 28 |
| neutral | 0.8696 | 115 |
| positive | 0.3333 | 57 |

## Sentiment confusion (expected \ predicted)

| expected \ predicted | negative | neutral | positive | unknown |
|---|---|---|---|---|
| negative | 3 | 18 | 2 | 5 |
| neutral | 0 | 100 | 8 | 7 |
| positive | 1 | 28 | 19 | 9 |
| unknown | 0 | 0 | 0 | 0 |

## Failure insights

- n_failed: **123**
- mode_counts: `{'subclass_miss': 103, 'sentiment_miss': 20}`

## Misclassification ledger

_123 rows; showing 100._

| mode | filename | expected subclass | predicted subclass | expected sent. | predicted sent. | reasoning |
|------|----------|-------------------|--------------------|-----------------|-----------------|-----------|
| subclass_miss | blair-l/inbox/88. | demand | email | neutral | neutral | The payload is a brief, informal internal message between colleagues routing a draft attachment for review, falling into the residual email category under rule  |
| subclass_miss | bass-e/deleted_items/252. | email | letter | positive | neutral | The document is an automated fantasy football standings and player status report delivered via email, functioning as a customer newsletter. Per rule 41 and rule |
| subclass_miss | lay-k/all_documents/956. | letter | email | neutral | neutral | The document is an internal corporate communication regarding SEC Form 4 filing requirements. It follows a standard email format with a subject line, salutation |
| subclass_miss | jones-t/deleted_items/12. | memo | notice | neutral | neutral | The document is explicitly titled 'Notice No. 01-417' and functions as an official exchange announcement to members regarding early market closing schedules for |
| subclass_miss | dasovich-j/inbox/800. | press_release | email | neutral | neutral | The document is an informal internal update with a subject line and brief body directing recipients to published FAQs regarding media coverage and regulatory in |
| subclass_miss | lavorato-j/old_inbox/85. | email | letter | positive | positive | The document is a customer-facing promotional invitation formatted as a business letter ('Dear... Sincerely...') advertising an online seminar. It follows the l |
| subclass_miss | baughman-d/inbox/346. | email | letter | neutral | positive | The document is a promotional customer newsletter/email blast advertising cash advances and loyalty points. Per rule 45(7), customer newsletters fall under the  |
| subclass_miss | baughman-d/deleted_items/32. | email | letter | neutral | neutral | The document is a daily news roundup/newsletter sent to a subscriber, featuring a 'Dear [Name]' salutation, broadcast segment previews, commodity prices, and su |
| subclass_miss | corman-s/inbox/archives/4. | email | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=8803, total_tokens=10849, comple |
| sentiment_miss | germany-c/_sent_mail/3. | email | email | positive | neutral | The document is an informal internal email thread between Enron employees coordinating the release of an invoice. It matches the residual 'email' subclass under |
| sentiment_miss | germany-c/sent_items/707. | email | email | neutral | positive | The document is a brief, informal acknowledgment of a fax receipt with a polite closing ('Thanks'), which fits the residual email subclass under the corresponde |
| subclass_miss | fischer-m/deleted_items/27. | email | notice | neutral | neutral | The document is an automated system notification informing the recipient that their expense report payment status has been updated to 'Paid.' It functions as a  |
| sentiment_miss | scott-s/deleted_items/448. | email | email | neutral | positive | The document is an internal club announcement regarding the 2002 Enron Running Club schedule, volunteer recruitment, and gear fundraising. It follows standard e |
| subclass_miss | shively-h/_sent_mail/207. | email | meeting_request | neutral | neutral | The payload is a calendar invitation for a recurring weekly status meeting, which directly matches the meeting_request subclass per rule 45. The content is pure |
| subclass_miss | lavorato-j/california/3. | email | meeting_request | negative | neutral | The document is an agenda outlining discussion topics and responsible parties for a scheduled call on 2-13-01. Its primary function is to provide an agenda-for- |
| sentiment_miss | germany-c/_sent_mail/80. | email | email | negative | neutral | The document is an informal email thread between colleagues updating each other on the status of legal documents, an addendum, and weekend plans. It lacks forma |
| subclass_miss | lewis-a/deleted_items/79. | email | letter | neutral | positive | The document is a promotional customer newsletter from eBay featuring Valentine's Day gift suggestions and special offers. Per rule 45, customer newsletters and |
| subclass_miss | ybarbo-p/inbox/150. | memo | email | positive | neutral | The document is an internal email thread between colleagues discussing the evaluation and response strategy for a third-party ship demurrage claim. It does not  |
| subclass_miss | kean-s/sent_items/230. | memo | email | neutral | neutral | Internal email thread between colleagues regarding the approval and distribution of an EEO policy memo. The payload matches the residual email category per rule |
| subclass_miss | bass-e/all_documents/272. | memo | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9029, total_tokens=11077, comple |
| subclass_miss | hayslett-r/projects/lng__global_/1. | memo | email | positive | neutral | Internal business communication sharing cost-of-service calculations and assigning follow-up analytical tasks to colleagues. Lacks formal demand, notice, or mee |
| subclass_miss | motley-m/inbox/ene_portland/administrative/19. | memo | email | neutral | neutral | The document is an internal forwarding of a voicemail message from HR to employees, structured as a brief email with a subject line and minimal body text. It co |
| subclass_miss | hain-m/all_documents/897. | memo | email | neutral | neutral | The document is an email transmission featuring a standard confidentiality disclaimer and a law-firm footer, forwarding an attached memorandum. It lacks substan |
| subclass_miss | jones-t/all_documents/5972. | memo | email | neutral | neutral | The document is an informal internal business message requesting a specific document (Memorandum of Association) from a colleague, lacking formal headers or leg |
| subclass_miss | mcconnell-m/all_documents/851. | memo | email | positive | neutral | The document is an internal email thread where an employee replies to a charity fundraising announcement with a routine inquiry about making donations while sta |
| subclass_miss | ermis-f/inbox/666. | memo | notice | neutral | neutral | The document is explicitly titled 'NWP System Notice' and functions as an official announcement to all shippers regarding updated fuel factors and rate schedule |
| subclass_miss | sanders-r/all_documents/255. | memo | email | negative | neutral | The document is an internal email updating colleagues on deposition progress and scheduling. It lacks formal demand, notice, or meeting-request markers, placing |
| subclass_miss | dickson-s/all_documents/132. | memo | email | neutral | neutral | Brief informal note between colleagues regarding routing a memo; lacks formal structure or specific function matching demand, notice, or memo subclass, falling  |
| subclass_miss | rogers-b/all_documents/440. | memo | meeting_request | neutral | positive | The payload is an informal email thread between colleagues whose explicit purpose is to schedule and confirm a lunch meeting, which directly matches the meeting |
| subclass_miss | nemec-g/all_documents/5291. | memo | email | neutral | neutral | The document is an informal internal message between colleagues assigning document review and approval tasks, which aligns with the email subclass. The content  |
| subclass_miss | fossum-d/all_documents/588. | memo | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9304, total_tokens=11350, comple |
| subclass_miss | kean-s/all_documents/5045. | memo | email | positive | neutral | Internal email thread between colleagues discussing the recent distribution of a memo. It lacks the formal structure or substantive content required for other s |
| subclass_miss | corman-s/all_documents/9. | memo | meeting_request | neutral | neutral | The payload is an email thread providing dial-in details and confirming the time for a scheduled conference call. Its primary function is to schedule/confirm a  |
| subclass_miss | shackleton-s/all_documents/8952. | memo | notice | neutral | neutral | The document is explicitly titled 'Notice No. 01-51' and functions as a formal regulatory announcement from NYMEX to its members regarding a margin rate change. |
| sentiment_miss | steffes-j/inbox/419. | memo | memo | positive | neutral | The document opens with a standard MEMORANDUM header containing TO/FROM/DATE/RE fields and functions as an internal policy briefing and coordination update rega |
| subclass_miss | dasovich-j/all_documents/8769. | memo | email | negative | positive | The payload is an internal corporate message thanking colleagues for their work and assigning follow-up drafting tasks, matching the residual email category und |
| subclass_miss | mann-k/_sent_mail/2750. | notice | email | positive | neutral | Internal Enron email thread between colleagues discussing contract details, delivery dates, and serial numbers for a turbine project. The content is routine and |
| subclass_miss | hyatt-k/projects/28. | notice | meeting_request | positive | neutral | The document is an email thread discussing technical specifications for the Big Sandy Project and explicitly proposes scheduling a follow-up meeting after May 2 |
| subclass_miss | dasovich-j/all_documents/4411. | notice | email | neutral | neutral | The document is an informal internal message forwarding a link to a regulatory draft decision without formal letter structure or functional markers like demands |
| subclass_miss | dasovich-j/all_documents/10684. | notice | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=13494, total_tokens=15540, compl |
| subclass_miss | mann-k/_sent_mail/2184. | notice | email | neutral | neutral | Internal informal email thread between colleagues discussing proofreading a notice and requesting a sanity check. The payload lacks formal legal or administrati |
| sentiment_miss | jones-t/all_documents/5967. | notice | notice | positive | neutral | The document is explicitly titled 'Notice No. 00-421' and functions as an official exchange announcement to members regarding temporary amendments to price fluc |
| subclass_miss | germany-c/_sent_mail/1345. | notice | email | neutral | neutral | Internal email thread between colleagues discussing a storage contract expiration and planned termination timeline. Classified as email per rule 45 cascade. Con |
| subclass_miss | lokay-m/all_documents/206. | notice | email | positive | neutral | The document is an internal email thread between colleagues requesting a summary of transport options in customer contracts following a staff meeting. It lacks  |
| subclass_miss | platter-p/deleted_items/11. | notice | letter | positive | positive | The payload is a promotional customer newsletter offering free games and prizes, which rule 45 step 7 explicitly classifies as a 'letter'. The enthusiastic, rew |
| subclass_miss | haedicke-m/all_documents/5022. | notice | email | neutral | positive | The document is a brief business communication forwarding regulatory background materials ahead of a scheduled conference call. It does not request a meeting, i |
| subclass_miss | rapp-b/inbox/115. | notice | email | positive | neutral | The document is an internal email thread between colleagues regarding HR transfer paperwork. It matches the residual 'email' subclass per rule 45, as the payloa |
| subclass_miss | kitchen-l/_americas/mexico/6. | notice | email | neutral | neutral | Internal clarification regarding a contractual notification obligation under a Power Purchase Agreement. Lacks formal demand, meeting, or notice markers, fallin |
| subclass_miss | hain-m/all_documents/250. | notice | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9491, total_tokens=11539, comple |
| subclass_miss | thomas-p/deleted_items/543. | notice | letter | positive | neutral | The document is a daily industry newsletter digest ('Daily Gas News') aggregating market updates, press releases, and financial reports. Per rule 45 step 7, a c |
| subclass_miss | kean-s/all_documents/8890. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8932, total_tokens=10980, comple |
| subclass_miss | horton-s/all_documents/69. | letter | meeting_request | neutral | neutral | The payload distributes a draft agenda for an upcoming Board meeting to directors, which squarely matches the meeting_request subclass per rule 45. The tone is  |
| subclass_miss | smith-m/inbox/419. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9743, total_tokens=11791, comple |
| subclass_miss | ring-r/deleted_items/289. | letter | email | positive | positive | The document is a welcome message explicitly referred to as an e-mail in its body. It follows a standard business greeting and closing format, provides account  |
| sentiment_miss | lay-k/all_documents/565. | letter | letter | positive | neutral | The document is a formal business communication featuring a standard salutation ('Dear Mr. Lay') and closing ('Yours faithfully'), functioning as a follow-up an |
| sentiment_miss | mims-thurston-p/deleted_items/67. | letter | letter | neutral | positive | The document is a customer welcome message introducing promotional services, formatted with a formal salutation and closing ('Dear Amazon Customer,' 'Sincerely, |
| subclass_miss | kaminski-v/all_documents/9712. | letter | meeting_request | positive | positive | The communication's primary purpose is to propose a follow-up visit and conversation between two professionals, which directly matches the meeting_request funct |
| subclass_miss | campbell-l/inbox/344. | letter | notice | negative | neutral | The payload is an official exchange/system announcement to market participants detailing a software release delay and new data postings, which functions as a no |
| subclass_miss | buy-r/inbox/438. | letter | meeting_request | negative | positive | The document is a formal invitation to speak at a conference, requesting a response and providing contact details. Its primary purpose is to invite participatio |
| subclass_miss | lay-k/all_documents/455. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8991, total_tokens=11039, comple |
| subclass_miss | campbell-l/inbox/669. | letter | meeting_request | neutral | neutral | The document is an email notification scheduling a Market Structure Working Group meeting, providing date, time, location, and teleconference details. Its prima |
| subclass_miss | shackleton-s/all_documents/8895. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9010, total_tokens=11056, comple |
| subclass_miss | kaminski-v/all_documents/5939. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9056, total_tokens=11104, comple |
| subclass_miss | thomas-p/deleted_items/183. | letter | email | neutral | neutral | The document is an internal email forwarding presentation materials for a scheduled working group meeting. It does not contain scheduling requests, formal deman |
| subclass_miss | rogers-b/deleted_items/302. | letter | notice | negative | neutral | The document is an official operational announcement from NYISO to market participants regarding a system issue and its resolution, which aligns with the 'notic |
| subclass_miss | lay-k/all_documents/240. | letter | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9787, total_tokens=11835, comple |
| subclass_miss | kitchen-l/_americas/eol/2. | press_release | email | neutral | neutral | The document is an informal internal message from Dave to Louise sharing a project activity list and deadlines. It lacks formal legal or corporate headings, fit |
| subclass_miss | shapiro-r/broadband_services/42. | press_release | email | negative | neutral | Internal business update listing legislative, regulatory, and coalition monitoring points alongside mentions of upcoming calls. Lacks formal memo headers or dem |
| subclass_miss | shankman-j/inbox/53. | press_release | email | neutral | neutral | The document is an informal internal message between colleagues sharing follow-up materials after a conference call. It lacks formal headings, demands, or meeti |
| subclass_miss | kean-s/all_documents/6036. | press_release | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9013, total_tokens=11059, comple |
| sentiment_miss | grigsby-m/all_documents/132. | press_release | press_release | positive | neutral | The document explicitly contains a 'NEWS RELEASE' header and 'FOR IMMEDIATE RELEASE' dateline with a media contact, which directly triggers the press_release su |
| subclass_miss | derrick-j/deleted_items/121. | press_release | meeting_request | neutral | neutral | The document is an internal message whose primary purpose is to relay a request for a meeting between Lay and Steve Kean during an existing appointment. This al |
| sentiment_miss | dasovich-j/all_documents/9891. | press_release | press_release | negative | neutral | The document is an email forwarding a 'FOR IMMEDIATE RELEASE' press release from the Office of the Governor regarding a request to FERC for wholesale power pric |
| subclass_miss | dasovich-j/all_documents/201. | press_release | memo | positive | neutral | The payload is an internal briefing and analysis summarizing state-level e-commerce tax proposals and stakeholder reactions, which aligns with the 'internal pol |
| subclass_miss | hain-m/all_documents/1318. | press_release | email | positive | neutral | The payload functions as an internal business email forwarding draft legal work-group documents and requesting peer review. Its tone is purely factual and routi |
| subclass_miss | hayslett-r/all_documents/470. | press_release | email | positive | positive | Internal informal email thread between colleagues discussing a news release and accounting decision; matches the email subclass per rule 45. Positive sentiment  |
| sentiment_miss | tholt-j/deleted_items/219. | press_release | press_release | negative | neutral | The document explicitly features 'NEWS RELEASE' and 'FOR IMMEDIATE RELEASE' headers along with a media contact, which directly matches the press_release subclas |
| sentiment_miss | dasovich-j/all_documents/2975. | press_release | press_release | positive | negative | The payload is explicitly identified as a forwarded press release in the subject line and follows standard press release formatting, including a headline, quote |
| subclass_miss | south-s/all_documents/26. | press_release | notice | neutral | neutral | The document is explicitly structured as a system notice with fields like 'Notice 2001041', 'Notice Type', and 'Effective Date of Notice', functioning as an off |
| subclass_miss | skilling-j/inbox/1228. | press_release | email | positive | positive | The document is a direct business outreach message formatted as an email, featuring a subject line, salutation, and informal closing. It functions as a promotio |
| sentiment_miss | buy-r/deleted_items/89. | press_release | press_release | positive | neutral | The message explicitly forwards two attached press releases from Viking, triggering the press_release subclass per rule 45. The content is purely informational  |
| subclass_miss | cash-m/all_documents/30. | demand | memo | negative | neutral | Internal performance update and work summary addressed to a supervisor, structured with clear section headings detailing transaction support, litigation, agreem |
| subclass_miss | taylor-m/all_documents/3517. | demand | email | negative | neutral | The document is an email thread between Enron personnel and outside counsel at Sullivan & Cromwell discussing proposed revisions to liability and indemnity clau |
| subclass_miss | lewis-a/deleted_items/442. | demand | email | positive | positive | The payload is a promotional sweepstakes message delivered via email. It lacks formal legal, regulatory, or business functions, falling into the residual email  |
| subclass_miss | ring-r/eesirenewableenergy/13. | demand | email | positive | neutral | The payload is an informal email thread between colleagues coordinating meter quantities, invoicing, and volume forecasts. It does not trigger any higher-priori |
| subclass_miss | campbell-l/all_documents/393. | demand | email | positive | neutral | Internal email thread between colleagues discussing environmental audit action items, third-party remediation responsibilities, and scheduling next steps. Match |
| subclass_miss | mann-k/all_documents/3627. | demand | email | negative | neutral | The text is a standalone contractual clause waiving consequential damages, lacking formal letterhead or signature blocks. Its presentation matches an internal e |
| subclass_miss | sanders-r/deleted_items/472. | demand | email | positive | neutral | Internal colleague email updating a recipient about a received arbitration notice and outlining next steps. Matches the 'email' subclass per rule 45 as an infor |
| subclass_miss | schoolcraft-d/inbox/junk/351. | demand | letter | positive | neutral | The document is a commercial industry newsletter ('RIGZONE Industry News') containing market updates, job postings, conference listings, and advertisements. Per |
| subclass_miss | arnold-j/deleted_items/243. | demand | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8939, total_tokens=10987, comple |
| subclass_miss | lavorato-j/deleted_items/300. | demand | email | negative | negative | The document is an internal email thread between colleagues discussing billing, settlements, and reconciliation processes. It lacks formal demands, meeting requ |
| subclass_miss | shackleton-s/inbox/767. | demand | email | neutral | neutral | Internal colleague email thread providing contact details and routing instructions regarding a default rate inquiry. Lacks formal demand, notice, or meeting-req |
| subclass_miss | shackleton-s/inbox/862. | demand | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8873, total_tokens=10921, comple |
| subclass_miss | blair-l/inbox/171. | demand | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9117, total_tokens=11163, comple |
| subclass_miss | mann-k/sent_items/39. | demand | email | neutral | neutral | The document is a brief, informal internal request asking a colleague to forward a notice of default and a draft response. It lacks formal legal phrasing, a TO/ |
| subclass_miss | bailey-s/deleted_items/253. | demand | email | neutral | neutral | The document is an internal workplace message from an Enron employee suggesting a minor formatting update to a log footer. It lacks formal memo headers or legal |
| subclass_miss | hain-m/all_documents/916. | demand | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9745, total_tokens=11793, comple |
| subclass_miss | germany-c/bankrupt/transport/trailblazer/5. | demand | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9119, total_tokens=11167, comple |
| subclass_miss | grigsby-m/all_documents/93. | demand | letter | negative | neutral | The payload is a customer newsletter providing routine updates on upcoming news segments and subscription management details. Per rule 41/45, an email announcin |
| subclass_miss | taylor-m/all_documents/2369. | demand | press_release | negative | neutral | The document is a Dow Jones Business News wire report featuring a dateline and headline announcing a corporate lawsuit, which directly matches the press_release |
