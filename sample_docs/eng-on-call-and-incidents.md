# Engineering: On-call and Incident Response

Routewise runs 24/7 for customers planning early-morning deliveries, so we keep an engineer on call at all times.

## Joining the rotation

- Engineers join the on-call rotation after **3 months** at YK Labs.
- Before your first shift, shadow one full week with an experienced engineer.
- Rotations are **one week long**. Handover is every **Monday at 10:00 UK time** in #eng-oncall.
- Swaps are fine: agree with a colleague and update the PagerDuty schedule yourself.

## On-call pay

- You get an on-call allowance of **£250 per week** of on-call, paid with your salary.
- If you are paged outside working hours and work for more than **1 hour**, you get **time off in lieu**, equal to the time worked, to be taken within 1 month.

## Severity levels

| Severity | Meaning | Response time |
| --- | --- | --- |
| SEV1 | Routewise is down or customer data is at risk | **15 minutes**, 24/7 |
| SEV2 | A major feature is broken for many customers | **30 minutes**, 24/7 |
| SEV3 | A minor feature is broken, or there is a workaround | Next working day |

## Running an incident

1. Acknowledge the page in PagerDuty.
2. For SEV1 or SEV2, create an incident channel named **#inc-YYYYMMDD-short-name**, for example #inc-20261106-login-errors.
3. Pick an **incident lead** (usually the on-call engineer) who coordinates and makes decisions.
4. Post updates in the incident channel at least every **30 minutes**.
5. For SEV1, the Customer Support lead updates the public status page at status.routewise.example.
6. When the problem is fixed, the incident lead declares the incident resolved in the channel.

## Postmortems

- SEV1 and SEV2 incidents need a written **postmortem within 5 working days**.
- Postmortems are **blameless**: focus on what in the system allowed the problem, not on who made a mistake.
- Use the postmortem template in Notion: timeline, impact, root cause, what went well, and action items with owners.
- Postmortems are reviewed in the weekly engineering meeting on **Wednesdays**.

## Escalation

If you cannot fix a problem within 30 minutes, escalate. Page the secondary on-call engineer, then the on-call engineering manager. Escalating early is always fine.
