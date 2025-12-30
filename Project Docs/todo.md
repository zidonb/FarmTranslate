# FarmTranslate - TODO

## Priority 1: User Feedback & Testing
- [ ] Get 10+ real users testing
- [ ] Collect feedback on translation quality
- [ ] Monitor actual usage patterns

## Priority 2: Cost Optimization
- [ ] Monitor translation costs (first month)
- [ ] Optimize prompt content (clarity & specificity)
- [ ] Optimize tokens (reduce context/history overhead)
- [ ] Test Gemini Flash vs Claude quality
- [ ] Switch to cheaper model if quality acceptable
- [ ] Add rate limiting (prevent abuse)

## Priority 3: Core Commands
- [ ] `/workers` - List connected workers (manager only)
- [ ] `/switch` - Switch active worker (multi-worker support)
- [ ] `/delete` - Remove worker connection
- [ ] `/reset` - Complete re-registration


- gemini-flash
- save all conversations for data, monitization.


- Menu look and feel
- cahce daily, save daily
- Language support in the registraion process
- I18N
- reset/cancel and so on - lemon squeezy events and check its working

- check feedback table and task table in dashboard. 
- save conversation of all time

- Multi-worker support


# Feature: Safety Incident Detection in `/daily` Command
### Changes to Prompt
Add new extraction category to the existing prompt:
```python
# Current categories:
- Action Items
- Safety Issues  
- Equipment

# Add new category:
- ⚠️ Safety Incidents Detected (NEW)

### Prompt Addition
```python
SAFETY INCIDENT DETECTION:
If the conversation contains reports of:
- Actual injuries or accidents
- Near-miss events (almost accidents)
- Immediate hazards that could cause injury
- Emergency situations

Add a special section:
⚠️ SAFETY INCIDENTS DETECTED:
- [Timestamp] [Specific incident with details]

Mark these with high priority and include who reported it.
```

### Example Output

**Before:**
```
📋 Daily Action Items (Last 24 Hours)

Action Items:
- Check cow 115 for heat
- Fix broken gate in section 3

Safety Issues:
- Electrical panel sparking - needs attention
```

**After (with incident detection):**
```
📋 Daily Action Items (Last 24 Hours)

⚠️ SAFETY INCIDENTS DETECTED:
- [10:23] Worker reported: Nearly slipped on wet floor in milking area - immediate hazard
- [14:15] Worker reported: Electrical panel sparking in barn section 2 - urgent attention needed

Action Items:
- Check cow 115 for heat
- Fix broken gate in section 3

Equipment:
- Milking machine #2 making noise
```

## Key Features
1. **Timestamp included** - Shows when incident was reported (important for logs)
2. **Who reported** - "Worker reported" creates accountability
3. **Severity language** - "immediate hazard", "urgent attention" emphasizes importance
4. **Separate section** - Visually distinct (⚠️ emoji + top placement)
5. **No false positives** - Only flag actual incidents/hazards, not hypotheticals
