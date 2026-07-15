# java-backend Adapter

Connect the conversation-core skeleton as a Filter into Spring Boot / Quarkus projects.

| Framework | Template | Default Target |
|:---|:---|:---|
| Spring Boot | `springboot/VoiceAgentFilter.java.tpl` | `src/main/java/com/example/voiceagent/VoiceAgentFilter.java` |
| Quarkus     | `quarkus/VoiceAgentFilter.java.tpl`    | Same as above |

## Configuration

`application.yml` / `application.properties`:

```yaml
skeleton:
  base-url: ${SKELETON_BASE_URL}
  api-prefix: ${API_PREFIX}
  route-prefix: ${ROUTE_PREFIX}
```

## Notes

- The template package `com.example.voiceagent` is replaced by the Agent during L1 rendering based on the user's actual project package name.
- Default `connectTimeout=3s`, `request timeout=10s`; adjustable as needed.
- Spring Boot registers `voiceAgentFilter` with order 10; should be placed before business Filters.
