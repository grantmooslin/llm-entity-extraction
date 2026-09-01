# Experiment report — qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42_attyall

Generated: 2026-08-30T02:25:34.545158+00:00

## Run metadata

- task: `correspondence_classification`
- prompt version: `sorter_docclass_correspondence_v2`
- model: `qwen/qwen3.7-flash`
- hf_repo: `Lucius-Morningstar/enron-correspondence-dedup`
- dataset size: `201`
- stratified / seed: `200 / 42`
- braintrust_logging: `True`
- git: `a448972`
- ground truth: `expected + expected_subclass + sentiment_label + sentiment_score`

## Aggregate scorers

- rows: **201** (errors: 0)
- doc_type_accuracy: **1.0000**
- subclass_accuracy: **0.5124** (equiv 0.5124)
- exact_match (doc_type ∧ subclass): **0.5124**
- sentiment_label_accuracy: **0.6119**
- sentiment_score_ok (band 0.25): **0.7760**
- sentiment_score_mae: **0.1599**
- correspondence_exact (type ∧ subclass ∧ sentiment label): **0.3881**
- confidence: **0.8590**

## Tokens / cost

- prompt tokens: `1691283`
- completion tokens: `259798`
- total cost: `—`

## Per-subclass accuracy

| subclass | accuracy | support |
|----------|----------|---------|
| attorney_demand | 0.2500 | 4 |
| demand | 0.0800 | 25 |
| email | 0.7234 | 47 |
| letter | 0.4800 | 25 |
| meeting_request | 0.8000 | 25 |
| memo | 0.3200 | 25 |
| notice | 0.4800 | 25 |
| press_release | 0.5600 | 25 |

## Subclass confusion (expected \ predicted)

| expected \ predicted | attorney_demand | demand | email | letter | meeting_request | memo | notice | other | press_release |
|---|---|---|---|---|---|---|---|---|---|
| attorney_demand | 1 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| demand | 0 | 2 | 11 | 2 | 0 | 1 | 1 | 7 | 1 |
| email | 0 | 0 | 34 | 5 | 3 | 1 | 2 | 2 | 0 |
| letter | 0 | 0 | 2 | 12 | 5 | 0 | 3 | 3 | 0 |
| meeting_request | 0 | 0 | 3 | 0 | 20 | 0 | 0 | 2 | 0 |
| memo | 0 | 0 | 11 | 0 | 2 | 8 | 3 | 1 | 0 |
| notice | 0 | 0 | 9 | 1 | 1 | 0 | 12 | 2 | 0 |
| other | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| press_release | 0 | 0 | 7 | 0 | 1 | 1 | 1 | 1 | 14 |

## Per-sentiment-label accuracy

| sentiment_label | accuracy | support |
|-----------------|----------|---------|
| negative | 0.0690 | 29 |
| neutral | 0.8696 | 115 |
| positive | 0.3684 | 57 |

## Sentiment confusion (expected \ predicted)

| expected \ predicted | negative | neutral | positive | unknown |
|---|---|---|---|---|
| negative | 2 | 21 | 2 | 4 |
| neutral | 0 | 100 | 7 | 8 |
| positive | 1 | 29 | 21 | 6 |
| unknown | 0 | 0 | 0 | 0 |

## Failure insights

- n_failed: **123**
- mode_counts: `{'subclass_miss': 98, 'sentiment_miss': 25}`

## Misclassification ledger

_123 rows; showing 100._

| mode | filename | expected subclass | predicted subclass | expected sent. | predicted sent. | reasoning |
|------|----------|-------------------|--------------------|-----------------|-----------------|-----------|
| subclass_miss | blair-l/inbox/88. | demand | email | neutral | neutral | The payload is a brief, informal internal message from one colleague to another regarding an attached draft notice and requesting approval. It lacks formal memo |
| subclass_miss | bass-e/deleted_items/252. | email | letter | positive | neutral | The document is an automated fantasy football e-report and league standings update delivered to subscribers. It functions as a customer newsletter, which falls  |
| subclass_miss | lay-k/all_documents/956. | letter | notice | neutral | neutral | The document is an internal corporate communication notifying employees about SEC Form 4 filing requirements and requesting transaction data. It functions as an |
| subclass_miss | jones-t/deleted_items/12. | memo | notice | neutral | neutral | The document is explicitly titled 'Notice No. 01-417' and functions as an official exchange announcement to members regarding corrected early closing schedules  |
| subclass_miss | dasovich-j/inbox/800. | press_release | email | neutral | neutral | Internal corporate communication providing routine guidance on handling media inquiries regarding SEC investigations and lawsuits. Directed to staff via an info |
| subclass_miss | cash-m/sent_items/383. | email | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9128, total_tokens=11176, comple |
| subclass_miss | lavorato-j/old_inbox/85. | email | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9491, total_tokens=11539, comple |
| sentiment_miss | baughman-d/inbox/346. | email | email | neutral | positive | The document is a commercial promotional email blast offering cash advances, featuring marketing copy, hyperlinks, and an unsubscribe footer. It lacks legal dem |
| subclass_miss | baughman-d/deleted_items/32. | email | letter | neutral | neutral | The document is a daily news newsletter and broadcast schedule sent to subscribers. Per rule 45, a community or customer newsletter delivered via email is class |
| sentiment_miss | germany-c/_sent_mail/3. | email | email | positive | neutral | The document is an informal internal email thread between colleagues discussing invoice timing. It lacks formal business letter formatting or legal demands, fit |
| subclass_miss | fischer-m/deleted_items/27. | email | notice | neutral | neutral | The document is an automated system notification informing the recipient that their expense report has been approved and paid. It functions as a system notice r |
| sentiment_miss | scott-s/deleted_items/448. | email | email | neutral | positive | The document is an informal internal communication regarding club membership, volunteer recruitment, and event planning. It lacks formal legal or administrative |
| subclass_miss | shively-h/_sent_mail/207. | email | meeting_request | neutral | neutral | The payload is a calendar invitation for a recurring weekly status meeting, which directly matches the meeting_request subclass per rule 45/46. The content is p |
| subclass_miss | lavorato-j/california/3. | email | meeting_request | negative | neutral | The document is an agenda outlining discussion topics and responsible parties for a scheduled call on 2-13-01. Its primary purpose is to prepare attendees for a |
| sentiment_miss | germany-c/_sent_mail/80. | email | email | negative | neutral | The document is an informal email thread between colleagues discussing the execution of legal documents and an addendum, concluding with casual weekend plans. I |
| sentiment_miss | lewis-a/deleted_items/79. | email | email | neutral | positive | The document is a promotional Valentine's Day newsletter/email from eBay featuring gift suggestions and payment options. It functions as a commercial email blas |
| subclass_miss | ybarbo-p/inbox/150. | memo | email | positive | neutral | The document is an internal email thread between Enron colleagues discussing the evaluation and validity of a shipping demurrage claim. The conversational excha |
| subclass_miss | kean-s/sent_items/230. | memo | email | neutral | neutral | Internal corporate email thread between colleagues regarding the review, signature, and distribution of an EEO policy memo. Fits the residual email category per |
| subclass_miss | bass-e/all_documents/272. | memo | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9029, total_tokens=11077, comple |
| subclass_miss | hayslett-r/projects/lng__global_/1. | memo | email | positive | neutral | The document is an internal workplace message sharing cost-of-service calculations and assigning follow-up tasks to colleagues. It lacks formal legal, regulator |
| subclass_miss | motley-m/inbox/ene_portland/administrative/19. | memo | email | neutral | neutral | The document is an internal corporate communication forwarding a voicemail message from an executive to employees, matching the email subclass based on its subj |
| subclass_miss | jones-t/all_documents/5972. | memo | email | neutral | neutral | The document is an informal internal message between colleagues requesting a specific administrative action (faxing a Memorandum of Association), which fits the |
| subclass_miss | mcconnell-m/all_documents/851. | memo | email | positive | positive | The document is an internal corporate email thread announcing a charity fundraising walk and soliciting volunteers, followed by a direct reply from a participan |
| subclass_miss | ermis-f/inbox/666. | memo | notice | neutral | neutral | The document is explicitly titled and formatted as a system notice ('NWP System Notice', 'All Shipper Letter') providing an official regulatory update on new fu |
| subclass_miss | sanders-r/all_documents/255. | memo | email | negative | neutral | The document is an informal internal update between colleagues regarding deposition progress and upcoming schedules, lacking formal headings or demands. It fits |
| subclass_miss | dickson-s/all_documents/132. | memo | email | neutral | neutral | The document is a brief, informal internal message between colleagues updating another on forwarding a memo, which fits the residual 'email' subclass under rule |
| subclass_miss | rogers-b/all_documents/440. | memo | meeting_request | neutral | positive | The payload is an informal email exchange between colleagues whose primary purpose is to schedule a lunch meeting ('scheduling things', 'shoot for early next we |
| subclass_miss | nemec-g/all_documents/5291. | memo | email | neutral | neutral | The document is an informal internal message from Steve to Pat assigning a document-comparison task and outlining approval routing steps. It lacks formal memora |
| subclass_miss | fossum-d/all_documents/588. | memo | email | neutral | neutral | Internal corporate email thread addressing a system glitch that caused erroneous mass emails; explains the issue, provides instructions to delete messages, and  |
| sentiment_miss | kean-s/all_documents/5045. | memo | memo | positive | neutral | Internal email thread forwarding a corporate memo for approval. Per rule 45 step 6, forwarding an attached memo subclasses as memo rather than email. The conten |
| subclass_miss | corman-s/all_documents/9. | memo | meeting_request | neutral | neutral | The document is an email thread providing dial-in numbers, passcodes, and time slots for a scheduled conference call. Its primary function is to confirm logisti |
| subclass_miss | shackleton-s/all_documents/8952. | memo | notice | neutral | neutral | The document is explicitly titled 'Notice No. 01-51' and functions as an official exchange announcement to NYMEX members regarding routine margin rate adjustmen |
| sentiment_miss | steffes-j/inbox/419. | memo | memo | positive | neutral | The document opens with a standard 'MEMORANDUM' header containing TO/FROM/DATE/RE fields and outlines internal coordination regarding a regulatory filing extens |
| subclass_miss | dasovich-j/all_documents/8769. | memo | email | negative | positive | Internal colleague communication featuring standard email routing headers (To/Cc/Subject) that assigns drafting tasks following a Senate hearing. Fits the email |
| subclass_miss | mann-k/_sent_mail/2750. | notice | email | positive | neutral | The document is an internal email thread between Enron colleagues discussing contract details, delivery dates, and serial numbers for a GE project. It contains  |
| subclass_miss | hyatt-k/projects/28. | notice | meeting_request | positive | neutral | The payload is an email thread focused on coordinating the Big Sandy Project interconnect. The sender explicitly proposes a specific timeframe for a follow-up m |
| subclass_miss | dasovich-j/all_documents/4411. | notice | email | neutral | neutral | Internal email forwarding a link to a regulatory draft decision and notice; routine, factual tone with no formal demand or notice language. |
| subclass_miss | dasovich-j/all_documents/10684. | notice | email | negative | neutral | The document is a compiled digest of external news articles and an editorial forwarded via email, indicated by the 'Subject:' header and the absence of formal m |
| subclass_miss | mann-k/_sent_mail/2184. | notice | email | neutral | neutral | The document is an informal internal email thread between colleagues discussing proofreading a notice. It lacks formal business structure or specific functional |
| sentiment_miss | jones-t/all_documents/5967. | notice | notice | positive | neutral | The document is explicitly titled 'Notice No. 00-421' and functions as an official exchange announcement to members regarding temporary amendments to price fluc |
| subclass_miss | germany-c/_sent_mail/1345. | notice | email | neutral | neutral | Internal email thread between colleagues discussing contract expiration dates and task delegation. Matches the residual 'email' subclass under rule 45. Content  |
| subclass_miss | lokay-m/all_documents/206. | notice | email | positive | neutral | Internal workplace email thread requesting colleagues to compile and forward a summary of transport options from customer contracts following a staff meeting. T |
| subclass_miss | platter-p/deleted_items/11. | notice | letter | positive | positive | The payload is a promotional customer newsletter offering free games and prizes, which matches the 'letter' subclass per rule 45(7) for community/vendor newslet |
| subclass_miss | haedicke-m/all_documents/5022. | notice | email | neutral | positive | The document is an internal business communication forwarding regulatory background materials ahead of a scheduled conference call. It lacks formal letter forma |
| subclass_miss | rapp-b/inbox/115. | notice | email | positive | positive | Internal colleague email thread regarding HR transfer forms and folder management. Fits the 'email' subclass per rule 45 as an informal administrative exchange. |
| subclass_miss | kitchen-l/_americas/mexico/6. | notice | email | neutral | neutral | The text is an internal clarification regarding a Power Purchase Agreement clause, explaining a notification requirement. It lacks formal legal demands or struc |
| subclass_miss | dasovich-j/all_documents/759. | notice | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=8803, total_tokens=10849, comple |
| sentiment_miss | hain-m/all_documents/250. | notice | notice | neutral | positive | The document explicitly titles itself a 'Notice' and functions as an official announcement to a stakeholder group regarding a meeting postponement and regulator |
| subclass_miss | thomas-p/deleted_items/543. | notice | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=12773, total_tokens=14819, compl |
| sentiment_miss | kean-s/all_documents/8890. | letter | letter | positive | neutral | The document follows a formal business letter format with a Dear/Sincerely structure, transmitting updates and requesting feedback on attached materials. It lac |
| subclass_miss | horton-s/all_documents/69. | letter | meeting_request | neutral | neutral | The communication distributes a draft agenda for an upcoming board meeting, directly matching the meeting_request subclass per rule 45. The content is purely in |
| subclass_miss | smith-m/inbox/419. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9743, total_tokens=11789, comple |
| subclass_miss | lay-k/all_documents/565. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9032, total_tokens=11080, comple |
| sentiment_miss | mims-thurston-p/deleted_items/67. | letter | letter | neutral | positive | The document is a customer welcome message introducing Amazon services, formatted with a 'Dear... Sincerely' structure and functioning as a welcome/subscription |
| subclass_miss | kaminski-v/all_documents/9712. | letter | meeting_request | positive | positive | The communication's core purpose is to propose a visit and subsequent discussion, satisfying the meeting_request subclass criteria. The tone is collegial and en |
| subclass_miss | campbell-l/inbox/344. | letter | notice | negative | neutral | The payload is an official system announcement directed to market participants regarding software release delays and new data postings, which squarely matches t |
| subclass_miss | buy-r/inbox/438. | letter | meeting_request | negative | positive | The document is a formal invitation to speak at a conference, requesting an RSVP and providing event details. Per rule 45, the primary purpose is to invite atte |
| subclass_miss | lay-k/all_documents/455. | letter | meeting_request | positive | positive | The communication's primary purpose is to confirm logistics and attendees for an upcoming executive meeting, which directly matches the meeting_request subclass |
| subclass_miss | campbell-l/inbox/669. | letter | meeting_request | neutral | neutral | The document's primary function is to announce and provide logistical details for a scheduled working group meeting, including date, time, location, and dial-in |
| subclass_miss | shackleton-s/all_documents/8895. | letter | email | positive | neutral | The document is a routine internal business inquiry requesting clarification on the correct Enron entity and contacts to initiate an ISDA Master Agreement negot |
| subclass_miss | thomas-p/deleted_items/183. | letter | email | neutral | neutral | The document is a brief internal email forwarding presentation materials for an upcoming working group meeting. It lacks formal demand, notice, or memo structur |
| subclass_miss | rogers-b/deleted_items/302. | letter | notice | negative | neutral | The document is an official broadcast to market participants regarding a system issue and its resolution, which aligns with the 'notice' subclass definition for |
| subclass_miss | lay-k/all_documents/240. | letter | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9787, total_tokens=11835, comple |
| subclass_miss | kitchen-l/_americas/eol/2. | press_release | email | neutral | neutral | The document is an informal internal message from a colleague sharing a project activity list and schedule. It lacks formal headings, demands, or official notic |
| subclass_miss | shapiro-r/broadband_services/42. | press_release | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9372, total_tokens=11418, comple |
| subclass_miss | shankman-j/inbox/53. | press_release | email | neutral | neutral | The payload is an informal internal message between colleagues referencing a prior call and promising to forward attachments. It lacks formal memo headers, lega |
| sentiment_miss | grigsby-m/all_documents/132. | press_release | press_release | positive | neutral | The document explicitly contains 'NEWS RELEASE' and 'For immediate release:' headers along with a dateline and media contact, which directly matches the press_r |
| subclass_miss | derrick-j/deleted_items/121. | press_release | meeting_request | neutral | neutral | The document is a brief internal communication notifying the recipient that Lay wants to schedule a meeting with Steve Kean regarding a press release. Its prima |
| subclass_miss | zipper-a/deleted_items/352. | press_release | email | neutral | neutral | The document is an internal email thread between colleagues discussing a draft press release attachment. It lacks formal notice/demand language or a structured  |
| sentiment_miss | dasovich-j/all_documents/9891. | press_release | press_release | negative | neutral | The document is an email forwarding a formally titled 'FOR IMMEDIATE RELEASE' press release from the Office of the Governor regarding a request to FERC for temp |
| subclass_miss | dasovich-j/all_documents/201. | press_release | memo | positive | neutral | The document functions as an informational briefing and policy analysis roundup regarding e-commerce taxation proposals. It presents an objective summary of com |
| subclass_miss | hain-m/all_documents/1318. | press_release | email | positive | neutral | The document is an informal FYI email forwarding draft legal agreements and requesting technical/legal reviews from colleagues. It does not contain demand, sche |
| subclass_miss | hayslett-r/all_documents/470. | press_release | email | positive | positive | The document is an informal internal message between colleagues discussing a news release and accounting decisions, fitting the email subclass. The writer expre |
| sentiment_miss | tholt-j/deleted_items/219. | press_release | press_release | negative | neutral | The document explicitly contains 'NEWS RELEASE' and 'FOR IMMEDIATE RELEASE' headers along with a media contact line, which directly matches the press_release su |
| sentiment_miss | dasovich-j/all_documents/2975. | press_release | press_release | positive | negative | The document is a forwarded transcript of Governor Davis's official remarks on a FERC report, functioning as a press release. The content expresses strong criti |
| subclass_miss | south-s/all_documents/26. | press_release | notice | neutral | neutral | The document is explicitly structured and labeled as a system notice ('Notice 2001041', 'Notice Type', 'Effective Date of Notice'), functioning as an official o |
| subclass_miss | skilling-j/inbox/1228. | press_release | email | positive | positive | The document is a promotional business outreach containing product updates and a referral commission offer. It lacks legal demands, regulatory notices, or meeti |
| sentiment_miss | buy-r/deleted_items/89. | press_release | press_release | positive | neutral | The document is an email forwarding two attached press releases from Viking. Per rules 45 and 46, a message whose payload is explicitly identified as a press re |
| subclass_miss | cash-m/all_documents/30. | demand | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9615, total_tokens=11663, comple |
| subclass_miss | taylor-m/all_documents/3517. | demand | email | negative | neutral | The document is an email thread between Enron and Sullivan & Cromwell discussing proposed revisions to contract clauses regarding liability and indemnity. It do |
| subclass_miss | lewis-a/deleted_items/442. | demand | email | positive | positive | The document is a promotional sweepstakes message formatted as an email, using enthusiastic, persuasive language to encourage action. It lacks formal legal, reg |
| subclass_miss | ring-r/eesirenewableenergy/13. | demand | email | positive | neutral | The payload is a routine business email thread between counterparties discussing meter quantities, discrepancies, and invoicing schedules. It does not contain f |
| subclass_miss | campbell-l/all_documents/393. | demand | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9210, total_tokens=11256, comple |
| subclass_miss | mann-k/all_documents/3627. | demand | email | negative | neutral | Classified as correspondence per explicit instruction. The text is a standard contractual clause limiting liability for consequential damages, lacking specific  |
| subclass_miss | sanders-r/deleted_items/472. | demand | email | positive | neutral | Internal corporate message between colleagues updating on a received arbitration notice and its potential merger impact. It does not issue a formal demand, sche |
| sentiment_miss | germany-c/sent_items/636. | demand | demand | negative | neutral | The document is an internal email thread forwarding a counterparty's demand letter regarding an unpaid invoice for post-petition gas deliveries. The explicit re |
| subclass_miss | schoolcraft-d/inbox/junk/351. | demand | letter | positive | neutral | The document is a commercial industry newsletter ('RIGZONE Industry News') aggregating headlines, events, and market data. Per rule 45, customer/community newsl |
| subclass_miss | arnold-j/deleted_items/243. | demand | notice | neutral | neutral | The document is an internal IT system announcement titled 'Final Notice' detailing a scheduled server migration and planned outage. It functions as an official  |
| subclass_miss | lavorato-j/deleted_items/300. | demand | email | negative | negative | The document is an internal email thread discussing billing and settlement reconciliation issues. It lacks formal demand, notice, or memo structures, fitting th |
| subclass_miss | shackleton-s/inbox/767. | demand | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8958, total_tokens=11006, comple |
| subclass_miss | haedicke-m/all_documents/902. | demand | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9208, total_tokens=11254, comple |
| subclass_miss | shackleton-s/inbox/862. | demand | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8873, total_tokens=10921, comple |
| subclass_miss | blair-l/inbox/171. | demand | email | positive | neutral | Internal business email updating colleagues on negotiation progress with Oneok, forwarding a draft dispute response, and noting upcoming actions. Matches the em |
| subclass_miss | mann-k/sent_items/39. | demand | email | neutral | neutral | The document is a brief internal request lacking formal headings or specific functional triggers (demand, notice, meeting, etc.), placing it in the residual ema |
| subclass_miss | bailey-s/deleted_items/253. | demand | email | neutral | neutral | Internal workplace message from an Enron employee suggesting a minor formatting improvement to a log. Lacks formal headers or legal demand language, fitting the |
| subclass_miss | hain-m/all_documents/916. | demand | other | negative | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=9745, total_tokens=11791, comple |
| subclass_miss | germany-c/bankrupt/transport/trailblazer/5. | demand | memo | negative | neutral | The document is an internal business directive instructing a colleague on how to draft a payment demand letter to a counterparty, providing specific financial f |
| subclass_miss | grigsby-m/all_documents/93. | demand | letter | negative | neutral | The document is a routine customer newsletter/broadcast update from Williams Energy News Live, explicitly addressing a subscriber ('Dear Mike') and providing pr |
| subclass_miss | taylor-m/all_documents/2369. | demand | press_release | negative | neutral | The document is a Dow Jones Business News wire report announcing a corporate lawsuit, featuring a standard dateline and copyright notice characteristic of a pre |
| subclass_miss | bailey-s/deleted_items/334. | demand | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=9093, total_tokens=11141, comple |
