# Part 3.3 - false hits (all thresholds)

## D09 (similar, similarity 0.9689) - false hit at 0.75, 0.80, 0.85, 0.90, 0.95

- **Incoming query:** Why are southbound trains skipping Convention Center station this morning?
- **Cached query matched (S09):** Why are northbound trains skipping Convention Center station this morning?
- **Similarity:** 0.9689
- **Cached answer returned:** Northbound trains may be skipping Convention Center station due to scheduled maintenance, service adjustments, or unexpected disruptions. First, check the transit authority's real-time service alerts for updates. Review the morning's schedule changes or maintenance notices on the transit website. For live updates, contact the transit hotline or use the official app. Riders should plan alternative routes or adjust travel times based on the latest information provided.
- **Correct answer (HW8 pipeline run on the incoming query):** Southbound trains may be skipping Convention Center station due to ongoing service adjustments. First, check the transit authority's official website for service alerts. If no updates are found, review the morning's schedule changes or delays announcements. If you still need real-time information, contact the transit hotline for updates specific to Convention Center station. Riders should plan alternative routes or adjust travel times accordingly.
- **Why the answers differ (label):** opposite direction; a different incident and platform

## D04 (similar, similarity 0.9410) - false hit at 0.75, 0.80, 0.85, 0.90

- **Incoming query:** What safety steps should the train operator follow if a train stops between stations?
- **Cached query matched (S04):** What safety steps should passengers follow if a train stops between stations?
- **Similarity:** 0.9410
- **Cached answer returned:** If a train stops between stations, stay calm and do not open the doors. Follow the instructions of transit staff or emergency personnel. If needed, use the emergency communication system to alert authorities. Remain in your seat and wait for assistance. Do not attempt to exit the train unless directed by staff. Your safety is the priority.
- **Correct answer (HW8 pipeline run on the incoming query):** If a train stops between stations, the operator should first secure the train doors and platform gates to ensure passenger safety. Next, they should immediately communicate with the control center to report the situation and request assistance. The operator must also follow emergency procedures to prevent unauthorized access to the train. Finally, they should wait for rescue or maintenance teams to safely move the train or assist any passengers in need. Riders should remain calm and follow any instructions from transit staff.
- **Why the answers differ (label):** operator procedure (radio control, secure train) instead of passenger guidance

## D02 (similar, similarity 0.9214) - false hit at 0.75, 0.80, 0.85, 0.90

- **Incoming query:** Why is the Green Line light rail delayed at Tasman station?
- **Cached query matched (S02):** Why is the Blue Line light rail delayed at Tasman station?
- **Similarity:** 0.9214
- **Cached answer returned:** The Blue Line light rail may be delayed at Tasman station due to scheduled maintenance, construction, or an unexpected incident. To find the most accurate and up-to-date information, check the transit authority's website or app for real-time updates. Look for service alerts or notifications related to Tasman station. Riders should plan accordingly and consider alternative routes if advised. Stay informed for the latest updates.
- **Correct answer (HW8 pipeline run on the incoming query):** The Green Line light rail may be delayed at Tasman station due to scheduled maintenance, construction, or an unexpected incident. To find the most accurate and up-to-date information, check the transit authority's website or app for real-time updates. Look for service alerts or notifications related to Tasman station. Riders should plan accordingly and consider alternative routes if advised. Stay informed for the latest updates.
- **Why the answers differ (label):** different line, so a different cause and different alternatives

## D07 (similar, similarity 0.8598) - false hit at 0.75, 0.80, 0.85

- **Incoming query:** How do I report a lost package left on a bus?
- **Cached query matched (S07):** How do I report a suspicious package left on a bus?
- **Similarity:** 0.8598
- **Cached answer returned:** If you find a suspicious package on a bus, do not touch it. Immediately alert the transit authority or emergency services. Provide details about the package's location, appearance, and any other relevant information to help authorities respond safely. Stay calm and follow their instructions. Your prompt action can help ensure the safety of everyone on the bus.
- **Correct answer (HW8 pipeline run on the incoming query):** If you find a lost package on a bus, locate it and notify the bus driver or transit staff right away. When you speak with them, provide details about the package, such as its size, color, and any identifying marks. Staff will take steps to ensure the package is safely handled and delivered to the rightful owner. Always act promptly to help return lost items to their owners.
- **Why the answers differ (label):** lost and found claim, not a security report (do not touch / call police)

## D01 (similar, similarity 0.8441) - false hit at 0.75, 0.80

- **Incoming query:** A bus on Route 23 caught fire at 1st and Santa Clara during the morning rush. What should riders do?
- **Cached query matched (S01):** A bus on Route 22 broke down at 1st and Santa Clara during the morning rush. What should riders do?
- **Similarity:** 0.8441
- **Cached answer returned:** Riders should check real-time updates for Route 22 via the transit app or website. Look for detour information or alternative routes provided by transit authorities. If necessary, consider using alternative transportation options like walking, biking, or a ride-share service to reach your destination. Stay informed and plan accordingly for the most up-to-date travel options.
- **Correct answer (HW8 pipeline run on the incoming query):** Riders should stay calm and move to a safe distance away from the bus. Immediately call 911 to alert emergency services. Avoid using electronic devices or open flames near the scene to prevent any additional risks. Do not attempt to retrieve belongings or approach the bus until authorities confirm it is safe to do so. Stay informed through official channels for further updates.
- **Why the answers differ (label):** fire means evacuate and keep clear, not wait for a replacement bus; different route

## D06 (similar, similarity 0.8369) - false hit at 0.75, 0.80

- **Incoming query:** Is the Orange Line running a bus bridge between Mountain View and Whisman during weekend track work?
- **Cached query matched (S06):** Is the Orange Line running a bus bridge between Mountain View and Whisman after the power outage?
- **Similarity:** 0.8369
- **Cached answer returned:** The Orange Line is currently operating with limited service due to the recent power outage. A bus bridge is in place between Mountain View and Whisman to assist with passenger transportation. Riders should check real-time updates via the transit agency’s website or app for the most accurate information. For the latest service details and any changes, please refer to official communication channels.
- **Correct answer (HW8 pipeline run on the incoming query):** The Orange Line may operate a bus bridge between Mountain View and Whisman during weekend track work, but the exact schedule depends on the track work dates. To confirm, check the official transit website for weekend track work schedules and any announcements about bus bridge services between Mountain View and Whisman. Riders should review the dates and times of the track work impact to plan their trip accordingly. For real-time updates, check the transit app or website before departure.
- **Why the answers differ (label):** planned weekend maintenance has a different schedule and notice than an outage

## D05 (similar, similarity 0.8248) - false hit at 0.75, 0.80

- **Incoming query:** How does the transit agency decide when an incident is resolved?
- **Cached query matched (S05):** How does the transit agency decide the severity level of an incident?
- **Similarity:** 0.8248
- **Cached answer returned:** The transit agency determines incident severity by reviewing its reporting guidelines, which outline criteria like injuries, property damage, and service disruption. They then assess how these factors affect public safety and the continuity of transit operations.
- **Correct answer (HW8 pipeline run on the incoming query):** The transit agency determines an incident is resolved when the issue no longer impacts safety or operations. This involves assessing if all affected systems are fully functional and no further risks exist. Once confirmed, the agency verifies the resolution through internal checks and monitoring. The agency then communicates the resolution to the public via official channels like social media, website updates, and customer service, ensuring riders are informed the incident is officially cleared. Riders should stay tuned to these updates for the latest information.
- **Why the answers differ (label):** asks about closing an incident, not about rating its severity
