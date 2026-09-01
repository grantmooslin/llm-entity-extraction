# Experiment report — qwen3.7-flash_sorter_docclass_correspondence_v3_enron200_s42

Generated: 2026-08-30T14:02:10.098487+00:00

## Run metadata

- task: `correspondence_classification`
- prompt version: `sorter_docclass_correspondence_v3`
- model: `qwen/qwen3.7-flash`
- hf_repo: `Lucius-Morningstar/enron-correspondence-dedup`
- dataset size: `200`
- stratified / seed: `200 / 42`
- braintrust_logging: `True`
- git: `1076761`
- ground truth: `expected + expected_subclass + sentiment_label + sentiment_score`

## Aggregate scorers

- rows: **200** (errors: 0)
- doc_type_accuracy: **1.0000**
- subclass_accuracy: **0.5600** (equiv 0.5600)
- exact_match (doc_type ∧ subclass): **0.5600**
- sentiment_label_accuracy: **0.6400**
- sentiment_score_ok (band 0.25): **0.7857**
- sentiment_score_mae: **0.1575**
- correspondence_exact (type ∧ subclass ∧ sentiment label): **0.4400**
- confidence: **0.8592**

## Tokens / cost

- prompt tokens: `1732025`
- completion tokens: `251507`
- total cost: `—`

## Per-subclass accuracy

| subclass | accuracy | support |
|----------|----------|---------|
| attorney_demand | 0.0000 | 2 |
| demand | 0.0000 | 1 |
| email | 0.6714 | 70 |
| letter | 0.4800 | 25 |
| meeting_request | 0.7200 | 25 |
| memo | 0.2800 | 25 |
| notice | 0.5185 | 27 |
| press_release | 0.5600 | 25 |

## Subclass confusion (expected \ predicted)

| expected \ predicted | attorney_demand | demand | email | letter | meeting_request | memo | notice | other | press_release |
|---|---|---|---|---|---|---|---|---|---|
| attorney_demand | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 0 |
| demand | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| email | 0 | 0 | 47 | 9 | 3 | 2 | 3 | 5 | 1 |
| letter | 0 | 0 | 3 | 12 | 5 | 0 | 3 | 2 | 0 |
| meeting_request | 0 | 0 | 4 | 0 | 18 | 0 | 0 | 3 | 0 |
| memo | 0 | 0 | 11 | 0 | 2 | 7 | 3 | 2 | 0 |
| notice | 0 | 0 | 10 | 2 | 1 | 0 | 14 | 0 | 0 |
| other | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| press_release | 0 | 0 | 5 | 0 | 0 | 0 | 1 | 5 | 14 |

## Per-sentiment-label accuracy

| sentiment_label | accuracy | support |
|-----------------|----------|---------|
| negative | 0.1071 | 28 |
| neutral | 0.9043 | 115 |
| positive | 0.3684 | 57 |

## Sentiment confusion (expected \ predicted)

| expected \ predicted | negative | neutral | positive | unknown |
|---|---|---|---|---|
| negative | 3 | 20 | 2 | 3 |
| neutral | 0 | 104 | 4 | 7 |
| positive | 1 | 27 | 21 | 8 |
| unknown | 0 | 0 | 0 | 0 |

## Failure insights

- n_failed: **112**
- mode_counts: `{'subclass_miss': 88, 'sentiment_miss': 24}`

## Misclassification ledger

_112 rows; showing 100._

| mode | filename | expected subclass | predicted subclass | expected sent. | predicted sent. | reasoning |
|------|----------|-------------------|--------------------|-----------------|-----------------|-----------|
| subclass_miss | sanders-r/px/19. | attorney_demand | email | neutral | neutral | The document is a brief cover email forwarding a draft arbitration demand for discussion at an upcoming committee meeting. It does not itself perform a demand s |
| subclass_miss | blair-l/inbox/88. | notice | email | neutral | neutral | The document is a brief internal note between colleagues attaching a draft notice for review and approval. It does not perform a formal notice, demand, or meeti |
| subclass_miss | bass-e/deleted_items/252. | email | letter | positive | neutral | The document is an automated fantasy football standings and player-status report functioning as a customer newsletter. It does not perform a legal, demand, or s |
| subclass_miss | lay-k/all_documents/956. | letter | notice | neutral | neutral | Internal corporate communication notifying employees of SEC Form 4 filing requirements and requesting transaction data if applicable. Functions as a regulatory  |
| subclass_miss | jones-t/deleted_items/12. | memo | notice | neutral | neutral | The document is explicitly titled 'Notice No. 01-417' and functions as an official exchange announcement to members regarding adjusted trading hours, which alig |
| subclass_miss | dasovich-j/inbox/800. | press_release | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9124, total_tokens=11172, comple |
| subclass_miss | lavorato-j/old_inbox/85. | email | letter | positive | positive | The document is a customer newsletter/email inviting premium members to an online seminar. It follows a formal business letter format with a salutation and sign |
| subclass_miss | baughman-d/inbox/346. | email | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=10340, total_tokens=12388, compl |
| subclass_miss | baughman-d/deleted_items/32. | email | letter | neutral | neutral | The document is a daily market and news newsletter broadcast to subscribers, which falls under the 'community or customer newsletter' category in rule 45 step 7 |
| sentiment_miss | germany-c/_sent_mail/3. | email | email | positive | neutral | Internal colleague email thread discussing invoice timing; lacks formal demand or legal phrasing, fitting the residual email category per rule 45. Sentiment is  |
| subclass_miss | fischer-m/deleted_items/27. | email | notice | neutral | neutral | Automated system notification regarding an expense report payment status; functions as a system notice per rule 45. Content is purely factual and routine, indic |
| subclass_miss | scott-s/deleted_items/448. | email | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9204, total_tokens=11250, comple |
| subclass_miss | shively-h/_sent_mail/207. | email | meeting_request | neutral | neutral | The payload is a calendar invitation for a recurring weekly status meeting, which directly matches the meeting_request subclass per rule 45. The content is pure |
| subclass_miss | lavorato-j/california/3. | email | meeting_request | negative | neutral | The document is an agenda listing discussion topics and assigned speakers for an upcoming conference call. Its primary purpose is to coordinate attendance and p |
| sentiment_miss | germany-c/_sent_mail/80. | email | email | negative | neutral | The payload is an informal, multi-participant email thread discussing document signing, legal fees, and weekend plans. It lacks formal business or legal structu |
| subclass_miss | lewis-a/deleted_items/79. | email | letter | neutral | positive | The document is a promotional vendor newsletter from eBay featuring Valentine's Day gift suggestions. It functions as a customer newsletter, which falls under t |
| subclass_miss | ybarbo-p/inbox/150. | memo | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9429, total_tokens=11477, comple |
| subclass_miss | kean-s/sent_items/230. | memo | email | neutral | neutral | Internal email thread coordinating the review and signature of an EEO policy memo; routine business coordination with polite, professional tone indicates neutra |
| subclass_miss | bass-e/all_documents/272. | memo | email | positive | positive | The document is an internal corporate announcement inviting employees to purchase discounted tickets for a sponsored bowl game, featuring promotional details an |
| subclass_miss | hayslett-r/projects/lng__global_/1. | memo | email | positive | neutral | The document is an internal business message sharing a spreadsheet and assigning analytical tasks to colleagues, matching the format and function of an email. T |
| subclass_miss | motley-m/inbox/ene_portland/administrative/19. | memo | email | neutral | neutral | The document is a brief internal forwarding note regarding a voicemail from an executive to employees, containing only contact information. It lacks formal dema |
| subclass_miss | jones-t/all_documents/5972. | memo | email | neutral | neutral | The text is an informal internal request between colleagues lacking formal memo or letter headers, fitting the residual email category under rule 45. The conten |
| subclass_miss | mcconnell-m/all_documents/851. | memo | email | positive | positive | The document is an internal email thread regarding a corporate charity fundraising walk, with a follow-up inquiry and the original announcement. It functions as |
| subclass_miss | ermis-f/inbox/666. | memo | notice | neutral | neutral | The document is explicitly titled 'NWP System Notice' and contains a 'Notice Text' section addressed to 'All Shippers' regarding a regulatory update on fuel fac |
| subclass_miss | sanders-r/all_documents/255. | memo | email | negative | neutral | The payload is an informal internal update between colleagues regarding deposition schedules and questions asked, structured with a subject line, salutation, an |
| subclass_miss | dickson-s/all_documents/132. | memo | email | neutral | neutral | Brief internal note between colleagues discussing forwarding a memo; lacks formal structure or specific functional markers, fitting the residual email category  |
| subclass_miss | rogers-b/all_documents/440. | memo | meeting_request | neutral | positive | The payload is an informal email thread between colleagues explicitly discussing scheduling a lunch meeting for early next week, which matches the meeting_reque |
| subclass_miss | nemec-g/all_documents/5291. | memo | email | neutral | neutral | Internal work instruction between colleagues regarding document comparison and approval workflow; lacks formal memo headers or external-facing elements, matchin |
| subclass_miss | fossum-d/all_documents/588. | memo | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9563, total_tokens=11611, comple |
| subclass_miss | kean-s/all_documents/5045. | memo | email | positive | neutral | The document is an informal internal email thread between colleagues discussing a previously issued memo. It lacks formal notice, demand, or meeting-request lan |
| subclass_miss | corman-s/all_documents/9. | memo | meeting_request | neutral | neutral | The payload's primary function is to distribute dial-in instructions and schedule a conference call to discuss a proposal, directly matching the meeting_request |
| subclass_miss | shackleton-s/all_documents/8952. | memo | notice | neutral | neutral | The document is explicitly titled 'Notice No. 01-51' and functions as an official exchange announcement to NYMEX members regarding margin rate adjustments. Its  |
| sentiment_miss | steffes-j/inbox/419. | memo | memo | positive | neutral | The document opens with a standard MEMORANDUM header containing TO/FROM/DATE/RE fields and coordinates internal regulatory strategy and comment-filing efforts,  |
| subclass_miss | dasovich-j/all_documents/8769. | memo | email | negative | positive | The document is an internal corporate email assigning follow-up tasks and thanking colleagues for their work on a Senate hearing. It lacks formal letterhead, de |
| subclass_miss | mann-k/_sent_mail/2750. | notice | email | positive | neutral | The document is an internal email thread between Enron employees discussing contract details, delivery dates, and serial numbers for a GE project. It lacks form |
| subclass_miss | hyatt-k/projects/28. | notice | meeting_request | positive | neutral | The top-level message explicitly proposes scheduling a follow-up meeting after May 25 to ensure key engineering and gas control personnel attend, which directly |
| subclass_miss | dasovich-j/all_documents/4411. | notice | email | neutral | neutral | The payload is an informal internal message forwarding a link to a regulatory draft decision without performing a formal function like demanding, notifying, or  |
| subclass_miss | dasovich-j/all_documents/10684. | notice | email | negative | neutral | The payload is an internal news digest compiling headlines and excerpts from multiple financial publications alongside an editorial. It lacks formal letter form |
| subclass_miss | mann-k/_sent_mail/2184. | notice | email | neutral | neutral | Internal informal email thread between colleagues discussing draft language for a notice; lacks formal business structure or specific functional triggers, fitti |
| sentiment_miss | jones-t/all_documents/5967. | notice | notice | positive | neutral | The document is explicitly titled 'Notice No. 00-421' and functions as an official exchange announcement to members regarding temporary amendments to trading pr |
| subclass_miss | germany-c/_sent_mail/1345. | notice | email | neutral | neutral | The document is an internal email thread between colleagues discussing a contract expiration and assigning follow-up tasks. It lacks formal demand, notice, or m |
| subclass_miss | lokay-m/all_documents/206. | notice | email | positive | neutral | The document is an internal workplace email requesting colleagues to compile contract option details into a spreadsheet following a staff meeting. It lacks form |
| subclass_miss | platter-p/deleted_items/11. | notice | letter | positive | positive | The payload is a promotional customer newsletter offering free games and prizes. Per rule 41, an email functioning as a customer newsletter subclasses as 'lette |
| subclass_miss | haedicke-m/all_documents/5022. | notice | email | neutral | positive | The document is an informal internal communication forwarding regulatory background materials ahead of a scheduled conference call. It does not schedule a meeti |
| subclass_miss | rapp-b/inbox/115. | notice | email | positive | neutral | Internal email thread between colleagues regarding employee transfer paperwork and administrative instructions. The payload matches an informal colleague commun |
| subclass_miss | kitchen-l/_americas/mexico/6. | notice | email | neutral | neutral | The document is an internal clarification regarding a contractual notice requirement for a Power Purchase Agreement. It lacks formal headings or demands, functi |
| subclass_miss | thomas-p/deleted_items/543. | notice | letter | positive | neutral | The document is a daily industry news digest/newsletter distributed to subscribers, aggregating market reports, corporate announcements, and policy updates. Und |
| subclass_miss | kean-s/all_documents/8890. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9191, total_tokens=11237, comple |
| subclass_miss | horton-s/all_documents/69. | letter | meeting_request | neutral | neutral | The communication's primary function is to distribute an agenda for an upcoming board meeting, which directly matches the meeting_request subclass per rule 45 s |
| sentiment_miss | lay-k/all_documents/565. | letter | letter | positive | neutral | The document is a formal vendor-to-executive communication with a standard salutation and closing, matching the 'letter' subclass per rule 45. The tone is profe |
| sentiment_miss | mims-thurston-p/deleted_items/67. | letter | letter | neutral | positive | The document follows a formal 'Dear... Sincerely' structure and functions as a customer welcome newsletter, which matches rule 45 step 7 for the letter subclass |
| subclass_miss | kaminski-v/all_documents/9712. | letter | meeting_request | positive | positive | The communication's primary purpose is to propose a follow-up visit and conversation between two professionals, which directly triggers the meeting_request subc |
| subclass_miss | campbell-l/inbox/344. | letter | notice | negative | neutral | The document is an official system/software update announcement directed to market participants regarding a deployment delay and new data postings, matching the |
| subclass_miss | buy-r/inbox/438. | letter | meeting_request | negative | positive | The document is a formal invitation to speak at a conference, which directly matches the meeting_request subclass per rule 45. The tone is courteous and profess |
| subclass_miss | lucci-p/deleted_items/421. | letter | email | positive | positive | The document is a promotional customer newsletter delivered electronically, containing no legal demands, notices, or meeting requests. Its upbeat, sales-oriente |
| subclass_miss | lay-k/all_documents/455. | letter | meeting_request | positive | positive | The document's primary purpose is to confirm a scheduled meeting and express appreciation for the opportunity, fitting the meeting_request subclass. The tone is |
| subclass_miss | campbell-l/inbox/669. | letter | meeting_request | neutral | neutral | The document's sole purpose is to announce and schedule a working group meeting with time, location, and dial-in details, which directly matches the meeting_req |
| subclass_miss | shackleton-s/all_documents/8895. | letter | email | positive | neutral | The document is a routine business inquiry email requesting guidance on the correct counterparty entity and procedural steps to initiate an ISDA Master Agreemen |
| subclass_miss | thomas-p/deleted_items/183. | letter | email | neutral | neutral | The document is a routine mailing-list email distributing presentation materials for a scheduled working group meeting. It does not perform a demand, notice, or |
| subclass_miss | rogers-b/deleted_items/302. | letter | notice | negative | neutral | The document is an official operational announcement from NYISO to market participants regarding a system issue and its resolution, which aligns with the 'notic |
| subclass_miss | lay-k/all_documents/240. | letter | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=10046, total_tokens=12092, compl |
| subclass_miss | kitchen-l/_americas/eol/2. | press_release | email | neutral | neutral | Internal routine update sharing a project activity list and timeline. Lacks formal demands, meeting requests, or official notices, fitting the residual email ca |
| subclass_miss | shapiro-r/broadband_services/42. | press_release | email | negative | neutral | The document is an internal status update regarding regulatory monitoring, coalition efforts, and upcoming meetings. It lacks formal demand, notice, or press-re |
| subclass_miss | shankman-j/inbox/53. | press_release | email | neutral | neutral | The document is an informal internal note between colleagues referencing a prior call and sharing draft materials for a joint venture. It lacks formal headings, |
| subclass_miss | kean-s/all_documents/6036. | press_release | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9272, total_tokens=11320, comple |
| sentiment_miss | grigsby-m/all_documents/132. | press_release | press_release | positive | neutral | The document explicitly features 'NEWS RELEASE' and 'FOR IMMEDIATE RELEASE' headers along with a dateline and media contact, directly matching the press_release |
| subclass_miss | derrick-j/deleted_items/121. | press_release | email | neutral | neutral | Brief internal message relaying logistical updates and a meeting arrangement between colleagues. Lacks formal headings or legal demands, fitting the residual em |
| sentiment_miss | dasovich-j/all_documents/9891. | press_release | press_release | negative | neutral | The document is an email chain whose payload is a formal 'FOR IMMEDIATE RELEASE' statement from the Office of the Governor requesting FERC price caps. Per rule  |
| subclass_miss | dasovich-j/all_documents/201. | press_release | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=10864, total_tokens=12912, compl |
| subclass_miss | hain-m/all_documents/1318. | press_release | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9867, total_tokens=11915, comple |
| subclass_miss | hayslett-r/all_documents/470. | press_release | email | positive | positive | The document is an informal internal message between colleagues discussing a news release and accounting decisions, lacking formal headers, demands, or official |
| sentiment_miss | tholt-j/deleted_items/219. | press_release | press_release | negative | neutral | The document explicitly contains 'NEWS RELEASE' and 'FOR IMMEDIATE RELEASE' headers, a media contact line, dateline, and standard press release formatting ('# # |
| sentiment_miss | dasovich-j/all_documents/2975. | press_release | press_release | positive | negative | The document is explicitly identified in the subject line and formatted as a press release/transcript of gubernatorial remarks regarding a FERC report, complete |
| subclass_miss | south-s/all_documents/26. | press_release | notice | neutral | neutral | The document is explicitly structured as an operational notice with fields like 'Notice Type,' 'Notice Title,' and 'Effective Date,' functioning as a routine sy |
| subclass_miss | skilling-j/inbox/1228. | press_release | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9561, total_tokens=11607, comple |
| sentiment_miss | buy-r/deleted_items/89. | press_release | press_release | positive | neutral | The email explicitly forwards attached press releases, triggering the press_release subclass under rule 45. The content is purely informational and routine rega |
| subclass_miss | cash-m/all_documents/30. | email | memo | negative | neutral | Internal professional update summarizing work accomplishments, structured as a briefing. Factual and routine tone indicates neutral sentiment. |
| sentiment_miss | taylor-m/all_documents/3517. | email | email | negative | neutral | The document is an email thread between corporate counsel and a client discussing proposed revisions to contract clauses regarding liability and indemnification |
| subclass_miss | lewis-a/deleted_items/442. | email | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9487, total_tokens=11533, comple |
| sentiment_miss | ring-r/eesirenewableenergy/13. | email | email | positive | neutral | The document is an informal email thread between colleagues discussing meter quantities, invoicing, and payment scheduling. It lacks formal demand, notice, or m |
| sentiment_miss | campbell-l/all_documents/393. | email | email | positive | neutral | The document is an internal email thread between colleagues coordinating environmental audit follow-ups and contractor responsibilities. It does not perform a f |
| subclass_miss | mann-k/all_documents/3627. | email | notice | negative | neutral | The payload is a formal contractual clause waiving consequential damages and limiting liability, functioning as a notice of terms. It lacks emotional or persuas |
| sentiment_miss | sanders-r/deleted_items/472. | email | email | positive | neutral | Internal colleague update regarding a third-party arbitration notice; lacks formal demand language or primary scheduling intent, falling into the residual email |
| sentiment_miss | germany-c/sent_items/636. | email | email | negative | neutral | Internal email thread among colleagues verifying facts before paying an attached demand letter for post-petition gas deliveries. It does not itself issue a dema |
| subclass_miss | schoolcraft-d/inbox/junk/351. | email | letter | positive | neutral | The document is a weekly industry newsletter from Rigzone featuring market data, job listings, and conference announcements. Under rule 45, a community or custo |
| subclass_miss | haedicke-m/all_documents/902. | demand | email | neutral | neutral | Internal colleague email thread forwarding attachments of guarantee demand letters and discussing procedural timing; per rules 46/47, an FYI cover note attachin |
| subclass_miss | shackleton-s/inbox/862. | email | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9132, total_tokens=11178, comple |
| sentiment_miss | blair-l/inbox/171. | email | email | positive | neutral | Internal colleague email thread coordinating a dispute settlement and forwarding a draft response; lacks formal demand, notice, or meeting-request functions, pl |
| sentiment_miss | germany-c/bankrupt/transport/trailblazer/5. | email | email | negative | neutral | Internal colleague communication providing instructions on drafting a payment demand letter; it does not itself perform a formal demand, placing it in the resid |
| subclass_miss | grigsby-m/all_documents/93. | email | letter | negative | neutral | The document is a customer newsletter/broadcast update from Williams Energy News Live containing schedule information and subscription links. Per rules 45 and 4 |
| subclass_miss | taylor-m/all_documents/2369. | email | press_release | negative | neutral | The payload is a Dow Jones Business News wire article reporting on a trademark infringement lawsuit, identifiable by its dateline, journalistic structure, and c |
| subclass_miss | campbell-l/inbox/80. | meeting_request | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9419, total_tokens=11465, comple |
| subclass_miss | zipper-a/deleted_items/376. | meeting_request | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9277, total_tokens=11325, comple |
| subclass_miss | cash-m/deleted_items/70. | meeting_request | email | positive | neutral | Internal informal message requesting advice on tracking down board compensation approval steps; lacks formal structure or specific functional triggers, fitting  |
| subclass_miss | sanders-r/inbox/38. | meeting_request | email | neutral | neutral | Internal coordination message discussing logistical preparation for upcoming meetings with opposing parties and technical staff. Lacks formal headings, demands, |
| subclass_miss | kaminski-v/all_documents/515. | meeting_request | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9586, total_tokens=11634, comple |
| sentiment_miss | cash-m/all_documents/146. | meeting_request | meeting_request | negative | neutral | The payload is an internal communication correcting a previously sent meeting invitation and explicitly instructing recipients to update their calendars to the  |
| subclass_miss | sanders-r/calendar/13. | meeting_request | email | negative | neutral | Internal corporate notification canceling a scheduled meeting. It lacks formal demand, notice, or scheduling language, placing it in the residual email category |
| subclass_miss | mccarty-d/sent_items/69. | meeting_request | email | neutral | neutral | The document is an automated Microsoft Outlook notification detailing delegate folder and calendar permissions. It performs no substantive legal or business fun |
| sentiment_miss | kean-s/all_documents/2163. | meeting_request | meeting_request | positive | neutral | The subject line explicitly states 'Meeting Invitation,' and the body provides logistical details and background for attending a presentation on December 18. Th |
