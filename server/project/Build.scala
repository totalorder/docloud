import sbt._
import Keys._
import play.Project._

object ApplicationBuild extends Build {

  val appName         = "Docloud"
  val appVersion      = "1.0-SNAPSHOT"

  val appDependencies = Seq(
    // Add your project dependencies here,
    jdbc,
    anorm,
    "org.apache.httpcomponents" % "fluent-hc" % "4.3.1"
  )


  val main = play.Project(appName, appVersion, appDependencies).settings(
    // Add your own project settings here      
  )

}
