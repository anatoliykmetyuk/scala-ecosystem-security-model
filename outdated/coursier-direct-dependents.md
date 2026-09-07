# Direct Coursier dependents in critical Scala infrastructure

This is a curated graph of direct production dependencies on the Coursier project family. It excludes sbt, test-only usage, CI actions, and tools that merely run on sbt.

```mermaid
flowchart LR
    CLI["Scala CLI"] -->|"core, CLI, JVM, launcher,<br/>archive cache, publishing"| C["Coursier project family"]
    MILL["Mill"] -->|"core, cache, archive cache,<br/>JVM management"| C
    BLOOP["Bloop"] -->|"core, JVM, interface"| C
    METALS["Metals"] -->|"core, interface,<br/>sbt Maven repositories"| C

    STEWARD["Scala Steward"] -->|"core, sbt Maven repositories"| C
    SCALADEX["Scaladex"] -->|"core, sbt Maven repositories"| C
    SCALAFIX["Scalafix"] -->|"core, interface"| C

    SCALA3["Scala 3 compiler / REPL"] -->|"Java interface"| C
    AMMONITE["Ammonite"] -->|"Java interface"| C
```

## Sources

- [Scala CLI](https://github.com/VirtusLab/scala-cli/blob/main/project/deps/package.mill)
- [Mill](https://github.com/com-lihaoyi/mill/blob/main/mill-build/src/millbuild/Deps.scala)
- [Bloop](https://github.com/scalacenter/bloop/blob/main/project/Dependencies.scala)
- [Metals](https://github.com/scalameta/metals/blob/main/build.sbt)
- [Scala Steward](https://github.com/scala-steward-org/scala-steward/blob/main/project/Dependencies.scala)
- [Scaladex](https://github.com/scalacenter/scaladex/blob/main/build.sbt)
- [Scalafix](https://github.com/scalacenter/scalafix/blob/main/project/Dependencies.scala)
- [Scala 3](https://github.com/scala/scala3/blob/main/project/Dependencies.scala)
- [Ammonite](https://github.com/com-lihaoyi/Ammonite/blob/main/build.mill)

“Coursier” is split across multiple coordinates, including `coursier`, `coursier-cache`, `coursier-jvm`, `coursier-sbt-maven-repository`, and `interface`. Querying only `coursier_2.13` would therefore miss immediate dependents.
