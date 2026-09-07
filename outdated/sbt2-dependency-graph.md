# sbt 2.0.7 dependency graph

Collapsed from the deps.dev Maven graph for `org.scala-sbt:sbt:2.0.7`, which contains 82 artifacts and 270 dependency edges.

```mermaid
flowchart TD
    S["sbt 2.0.7"]

    S --> MAIN["main_3 2.0.7"]
    S --> IO["sbt IO 1.12.2"]
    S --> SL["Scala 3 library 3.8.4"]

    MAIN --> CORE["Core sbt modules<br/>actions · tasks · commands · settings · run"]
    MAIN --> LM["Library management"]
    MAIN --> ZINC["Zinc 2.0.4"]
    MAIN --> DATA["Protocols and serialization"]
    MAIN --> TERM["Terminal, filesystem and native integration"]
    MAIN --> UTIL["Caching and concurrency"]

    ZINC --> COMPILER["Scala 3 compiler · TASTy · ASM"]

    LM --> IVY["sbt fork of Apache Ivy"]
    LM -. "shaded implementation" .-> COURSIER["Coursier 2.1.25-M26"]
    LM --> NETWORK["Gigahorse · Apache HttpClient 5<br/>SSL Config · JSch · Typesafe Config"]

    DATA --> JSON["Contraband · sjson-new · Jawn<br/>ScalaJSON · shaded Gson"]

    TERM --> TERMINAL_LIBS["JLine 2 fork + JLine 3 · JAnsi<br/>JNA · IPC socket · Swoval"]

    UTIL --> CACHE["Caffeine · LMAX Disruptor<br/>Reactive Streams · Scala collections"]

    S -. "separately packaged plugin" .-> REMOTE["sbt remote cache"]
    REMOTE -.-> BAZEL["Bazel-compatible remote APIs"]
```

Solid edges represent the collapsed published runtime graph. Dashed edges identify shaded, build-time, or separately packaged components discovered from the source build.

Sources:

- [deps.dev dependency graph](https://deps.dev/maven/org.scala-sbt%3Asbt/2.0.7/dependencies)
- [deps.dev API documentation](https://docs.deps.dev/api/v3alpha/)
- [sbt technology-stack documentation](/Users/anatolii/Projects/sbt/contributing-docs/07_tech_stack.md)
- [sbt dependency declarations](/Users/anatolii/Projects/sbt/project/Dependencies.scala)
