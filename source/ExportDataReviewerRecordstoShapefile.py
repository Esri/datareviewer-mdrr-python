# ---------------------------------------------------------------------------
# Created By: The ArcGIS Data Reviewer Team

# Copyright 2020 Esri

# Licensed under the Apache License, Version 2.0 (the "License"); You
# may not use this file except in compliance with the License. You may
# obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

# A copy of the license is available in the repository's
# LICENSE file.

# Description:
# Exports the reviewer errors from the selected Reviewer workspace session to
# shapefiles.  One point shapefile will be created. The XY location of line and
# polygon errors will be calculated and included in the output point shapefile.
# If errors exist without associated geometry in the selected sessions, these
# records will be exported to a dbf table.

# Disclaimer:
# Due to the complex relationship of tables within the Reviewer Workspace,
# modifying the content of this script is not recommended.  If you would like
# changes or enhancements to this script, please comment on the template
# through the Resource Center.

# Last Modified: 11/27/2019
# ---------------------------------------------------------------------------

# Import necessary modules
import arcpy
import os
import shutil
import sys
import datetime

# Importing license level
try:
    import arcinfo
except:
    arcpy.AddError("This tool requires an ArcInfo license.")
    sys.exit("ArcInfo license not available")

##Script arguments
ReviewerWorkspace = arcpy.GetParameterAsText(0)
Sessions = arcpy.GetParameterAsText(1)
Fields = arcpy.GetParameterAsText(2)
Workspace = arcpy.GetParameterAsText(3)
ShapeName = arcpy.GetParameterAsText(4)


SessionsList = Sessions.split(";")
FieldsList = Fields.split(";")

# Script functions
def Renamefield_Pro(temp_shape, temp_out, workspace, ShapeFileName):
    
    RenameFields = ["ORIGINTABLE", "ORIGINCHECK", "REVIEWSTATUS", "CORRECTIONSTATUS", "VERIFICATIONSTATUS", "REVIEWTECHNICIAN", "REVIEWDATE", "CORRECTIONTECHNICIAN", "CORRECTIONDATE", "VERIFICATIONTECHNICIAN", "VERIFICATIONDATE", "LIFECYCLESTATUS", "LIFECYCLEPHASE"]
    NewNames = ["ORIG_TABLE", "ORIG_CHECK", "ERROR_DESC", "COR_STATUS", "VER_STATUS", "REV_TECH", "REV_DATE", "COR_TECH", "COR_DATE", "VER_TECH", "VER_DATE", "STATUS", "PHASE"]

    arcpy.CopyFeatures_management(temp_shape, temp_out)
    
    fields = arcpy.ListFields(temp_out)  #get a list of fields for each feature class

    for field in fields:    
        if "REVTABLEMAIN" in field.name:
            if field.type == "OID" or field.type == "Geometry" :
                continue
            if "OBJECTID" in field.name:
                ## Manage OID field
                arcpy.AddField_management(temp_out, "FeatureOID", field.type)
                expr = "!" + field.name + "!"
                arcpy.CalculateField_management(temp_out, "FeatureOID", expr, "PYTHON3")
                arcpy.DeleteField_management(temp_out, field.name)
                continue
            
            fieldNames = field.name.split("_")
            outname = fieldNames[1]
            if fieldNames[1] in RenameFields:
                i = RenameFields.index(outname)
                outname = NewNames[i]
            # add a new field using the same properties as the original field
            arcpy.AddField_management(temp_out, outname, field.type)

            # calculate the values of the new field
            # set it to be equal to the old field       
            exp = "!" + field.name + "!"
            arcpy.CalculateField_management(temp_out, outname, exp, "PYTHON3")

            # delete the old fields
            arcpy.DeleteField_management(temp_out, field.name)
        else:
            if field.type == "OID" or field.type == "Geometry" :
                continue
            arcpy.DeleteField_management(temp_out, field.name)
     
    ##Save the layer as a shapefile
    arcpy.FeatureClassToShapefile_conversion(temp_out, workspace)
    shape_1 = workspace + "\\tmp_out.shp"
    arcpy.Rename_management(shape_1, ShapeFileName)



# Check if shapefiles created by script exists. If so error and do not process.
if ".shp" in ShapeName:
    FileName = ShapeName[:-4] + "_Table.dbf"
else:
    FileName = ShapeName + "_Table.dbf"
    ShapeName = ShapeName + ".shp"

FinalPointShape = Workspace + "\\" + ShapeName
Table = Workspace + "\\" + FileName

# Create a temporary database for processing errors
now = datetime.datetime.now()

if arcpy.GetInstallInfo()['ProductName'] == 'Desktop':
	gdbname = now.strftime("%Y%m%dT%H%M%S") + ".mdb"
else :
	gdbname = now.strftime("%Y%m%dT%H%M%S") + ".gdb"
arcpy.AddMessage("Product is  " + arcpy.GetInstallInfo()['ProductName'])

TempWksp = Workspace + "\\Temp\\" + gdbname
TempDir = Workspace + "\\Temp"
os.mkdir(TempDir)
arcpy.AddMessage("Temp = " + TempWksp)

if arcpy.GetInstallInfo()['ProductName'] == 'Desktop':
	arcpy.CreatePersonalGDB_management(Workspace + "\\Temp", gdbname)
else :
	arcpy.CreateFileGDB_management(Workspace + "\\Temp", gdbname)

LineShape = TempWksp + "\\RevLine"
PolyShape = TempWksp + "\\RevPoly"
LineShapeSingle = TempWksp + "\\RevLine_single"
LineShapeDissolve = TempWksp + "\\RevLine_dissolve"
PolyShapeSingle = TempWksp + "\\RevPoly_single"
PolyShapeDissolve = TempWksp + "\\RevPoly_dissolve"
TempFC = TempWksp + "\\TempPoint"

# Paths to tables in Reviewer workspace
SessionsTable = ReviewerWorkspace + "\\REVSESSIONTABLE"
REVTABLEMAIN = ReviewerWorkspace + "\\REVTABLEMAIN"
REVTABLEPOINT = ReviewerWorkspace + "\\REVDATASET\\REVTABLEPOINT"
REVTABLELINE = ReviewerWorkspace + "\\REVDATASET\\REVTABLELINE"
REVTABLEPOLY = ReviewerWorkspace + "\\REVDATASET\\REVTABLEPOLY"

Exists = False

if not arcpy.Exists(Workspace):
    os.makedirs(Workspace)

# Check to see if output shapefile already exists. If exists do not process.
if arcpy.Exists(FinalPointShape):
    arcpy.AddError("Point shapefile already exists in output workspace " \
    + FinalPointShape)
    Exists = True
if arcpy.Exists(Table):
    arcpy.AddError("Table for non geometry errors already exists in output " \
    + "workspace " + Table)
    Exists = True

if Exists == False:

    # Local variables:
    TableFields = Fields

    RenameFields = ["ORIGINTABLE", "ORIGINCHECK", "REVIEWSTATUS",
    "CORRECTIONSTATUS", "VERIFICATIONSTATUS", "REVIEWTECHNICIAN", "REVIEWDATE",
    "CORRECTIONTECHNICIAN", "CORRECTIONDATE", "VERIFICATIONTECHNICIAN",
    "VERIFICATIONDATE", "LIFECYCLESTATUS", "LIFECYCLEPHASE"]
                                            
    NewNames = ["ORIG_TABLE", "ORIG_CHECK", "ERROR_DESC", "COR_STATUS",
    "VER_STATUS", "REV_TECH", "REV_DATE", "COR_TECH", "COR_DATE",
    "VER_TECH", "VER_DATE", "STATUS", "PHASE"]

    PointFieldInfo = "REVTABLEPOINT.SHAPE SHAPE VISIBLE NONE; " \
    + "REVTABLEPOINT.OID REVTABLEPOINT.OID HIDDEN NONE; " \
    + "REVTABLEPOINT.LINKGUID REVTABLEPOINT.LINKGUID HIDDEN NONE; " \
    + "REVTABLEPOINT.SESSIONID SESSIONID HIDDEN NONE; "
    TableFieldInfo = "; "

    try:
        sessionIDs = []
        WhereClause = ""
        TotalErrors = 0

        # -------------------------------------------------------
        # Determine what fields will be in output shapefile\table
        # -------------------------------------------------------

        # Get RevTableMain and RevTablePoint fully qualified names
        arcpy.env.workspace = ReviewerWorkspace
        tableList = arcpy.ListTables()
        for table in tableList:
            if "REVTABLEMAIN" in table:
                RevMainFullName = table + "."

        fcList = arcpy.ListFeatureClasses("", "", "REVDATASET")
        for fc in fcList:
            if "REVTABLEPOINT" in fc:
                RevPointFullName = fc + "."

        PointFieldInfo = "SHAPE SHAPE VISIBLE NONE; " + RevPointFullName \
        + "OBJECTID OID HIDDEN NONE; TempPoint.LINKGUID TempPoint.LINKGUID HIDDEN " \
        + "NONE; TempPoint.SESSIONID TempPoint.SESSIONID HIDDEN NONE; "
        TableFieldInfo = "; "

        # Get the fields in RevTableMain
        desc = arcpy.Describe(REVTABLEMAIN)
        for field in desc.fields:
            name = field.name

            # For each field determine if it will be visible in output based on
            # fields input value
            view = "HIDDEN"
            if name in FieldsList:
                view = "VISIBLE"

            # If the field is over 10 characters (in RenameFields array)
            # replace with new name (from NewNames array).
            outname = name
            if name in RenameFields:
                i = RenameFields.index(name)
                outname = NewNames[i]

            # Update the information of the shapefile and table outputs
            PointFieldInfo = PointFieldInfo + RevMainFullName + name + " " \
            + outname + " " + view + " NONE; "

            TableFieldInfo = TableFieldInfo + name + " " + outname + " " \
            + view + " NONE; "

        # Trim last characters from output strings
        PointFieldInfo = PointFieldInfo[:-2]
        TableFieldInfo = TableFieldInfo[:-2]

        # ---------------------------------------------------------
        # Build the whereclause to select the input session records
        # ---------------------------------------------------------

        # Get the Session ID(s)
        rows = arcpy.SearchCursor(SessionsTable)
        RowCount = int(arcpy.GetCount_management(SessionsTable).getOutput(0))
        for row in rows:

            # I am interested in the value in column SessionName
            if row.SESSIONNAME in Sessions:
                sessionIDs.append(str(row.SESSIONID))

        # Delete cursor and row objects to remove locks on the data
        del row
        del rows

        SessionCount = len(sessionIDs)

        # If you did not select all the session, make a whereclause to select
        # only features from the desired sessions
        if SessionCount != RowCount:
            WhereClause = "("
            SessionFieldName = arcpy.AddFieldDelimiters(ReviewerWorkspace,
            "SessionID")

            for sessionID in sessionIDs:
                WhereClause = WhereClause + SessionFieldName + " = " \
                + str(sessionID) + " OR "

            WhereClause = WhereClause[:-4] + ")"

        WhereCount = len(WhereClause)

        # Expression parameter of make layer and create table view only allows
        # 247 characters.

        # If the number of sessions selected is more than 13 this limit will
        # be reached.

        if WhereCount > 222:

            # Return error and do not process records
            arcpy.AddMessage(WhereClause)
            arcpy.AddMessage("Whereclause length " + str(WhereCount))
            arcpy.AddError("Too many sessions were selected. The whereclause " \
            + "for selecting only records from the chosen session will be too " \
            + "long. You must select less than 12 sessions or you must " \
            + "select all.")

        else:

            # ----------------------
            # Add XY to Point Errors
            # ----------------------

            count = 0
            arcpy.AddMessage("\nProcessing Point Errors...")

            # Make a point layer and join to RevTableMain to get error
            # information
            arcpy.MakeFeatureLayer_management(REVTABLEPOINT, "TempPoint",
            WhereClause, "", "")

            count = int(arcpy.GetCount_management("TempPoint").getOutput(0))

            arcpy.AddMessage("  .. " + str(count) \
            + " point features will be processed.")

            TotalErrors = TotalErrors + count

            arcpy.FeatureClassToFeatureClass_conversion("TempPoint",
            TempWksp, "TempPoint")

            # -------------------------------
            # Add Line Errors to XY Shapefile
            # -------------------------------

            count = 0

            arcpy.AddMessage("\nProcessing Line Errors...")

            # Make Line Layer with only records from selected sessions
            arcpy.MakeFeatureLayer_management(REVTABLELINE, "RevLine",
            WhereClause, "", "")

            count = int(arcpy.GetCount_management("RevLine").getOutput(0))

            if count >= 1:
                arcpy.AddMessage("  .. " + str(count) + " line features will " \
                + "be processed.")
                arcpy.AddMessage("  .. Converting line geometry to point.")

                # --- Handle multi-part geometries ---
                # Explode into single part features
                arcpy.MultipartToSinglepart_management("RevLine",
                LineShapeSingle)

                # Run repair geometry incase any bad geometry created.
                arcpy.RepairGeometry_management(LineShapeSingle)

                # Create a point for each part
                arcpy.FeatureToPoint_management(LineShapeSingle, LineShape,
                "INSIDE")

                # Dissolve the points into a multi-part point using the LinkGUID
                # field
                arcpy.Dissolve_management(LineShape, LineShapeDissolve,
                "LINKGUID", "", "MULTI_PART", "DISSOLVE_LINES")

                TotalErrors = TotalErrors + count

                arcpy.Append_management(LineShapeDissolve, TempFC, "NO_TEST",
                "")

            else:
                arcpy.AddMessage("  .. No line errors exist in selected " \
                + "session.")

            # ----------------------------------
            # Add Polygon Errors to XY Shapefile
            # ----------------------------------

            count = 0

            # Make Polygon Layer with only records from selected sessions
            arcpy.AddMessage("\nProcessing Polygon Errors...")
            arcpy.MakeFeatureLayer_management(REVTABLEPOLY, "RevPoly",
            WhereClause, "", PointFieldInfo)

            count = int(arcpy.GetCount_management("RevPoly").getOutput(0))

            if count >= 1:
                arcpy.AddMessage("  .. " + str(count) + " polygon features " \
                + "will be exported to shapefile.")
                arcpy.AddMessage("  .. Converting polygon geometry to point.")

                # --- Handle multi-part geometries ---
                # Explode into single part features
                arcpy.MultipartToSinglepart_management("RevPoly",
                PolyShapeSingle)

                # Run repair geometry incase any bad geometry created.
                arcpy.RepairGeometry_management(PolyShapeSingle)

                # Create a point for each part
                arcpy.FeatureToPoint_management(PolyShapeSingle, PolyShape,
                "INSIDE")

                # Dissolve the points into a multi-part point using the
                # LinkGUID field
                arcpy.Dissolve_management(PolyShape, PolyShapeDissolve,
                "LINKGUID", "", "MULTI_PART", "DISSOLVE_LINES")

                TotalErrors = TotalErrors + count

                arcpy.Append_management(PolyShapeDissolve, TempFC, "NO_TEST",
                "")

            else:
                arcpy.AddMessage("  .. No polygon errors exist in selected " \
                + "session.")

            arcpy.MakeFeatureLayer_management(TempFC, "Final_pt", "", "", "")
            arcpy.AddMessage("  .. Joining to RevTableMain for error " \
            + "information.")
            arcpy.AddJoin_management("Final_pt", "LINKGUID", REVTABLEMAIN,
            "ID", "KEEP_COMMON")
            
            # Make new layer with appropriate output field names
            shape = ShapeName[:-4]
            arcpy.MakeFeatureLayer_management("Final_pt", shape, "", "",
            PointFieldInfo)
            count = int(arcpy.GetCount_management(shape).getOutput(0))

            arcpy.AddMessage("\nCreating point shapefile.")
            shape_out = ShapeName[:-4]
            
            if arcpy.GetInstallInfo()['ProductName'] == 'Desktop':           
                # Save the layer as a shapefile
                arcpy.FeatureClassToShapefile_conversion(shape, Workspace)
            else:
                tmp_out = TempWksp + "\\tmp_out"
                Renamefield_Pro(shape, tmp_out, Workspace, ShapeName)


            # -------------------------------
            # Process Errors with no geometry
            # -------------------------------

            arcpy.AddMessage("\nProcessing errors with no geometry...")
            count = 0

            # To find only table records, add the GeometryType field records
            # that are null to the list
            GeoFieldName = arcpy.AddFieldDelimiters(ReviewerWorkspace,
            "GEOMETRYTYPE")
            if SessionCount != RowCount:
                WhereClause = WhereClause + " AND " + GeoFieldName + " IS NULL"
            else:
                WhereClause = GeoFieldName + " IS NULL"

            # Create a table view of records that meet query
            arcpy.MakeTableView_management(REVTABLEMAIN, "RevTable",
            WhereClause, "#", TableFieldInfo)
            count = int(arcpy.GetCount_management("RevTable").getOutput(0))

            # If errors with no geometry exist
            if count >= 1:
                TotalErrors = TotalErrors + count
                arcpy.AddMessage("  .. " + str(count) + " errors exist with " \
                + "no geometry and will be exported to a table.")

                # Create the .dbf table of errors
                arcpy.TableToTable_conversion("RevTable", Workspace, FileName)

            else:
                arcpy.AddMessage("No errors exist with no geometry in " \
                + "selected session.  No table will be created.")

            # Provide summary information about processing
            arcpy.AddMessage("\nTotal Errors Exported: " + str(TotalErrors))
            arcpy.AddMessage("Output shapefile path " + FinalPointShape)
            if count >= 1:
                arcpy.AddMessage("Output Table path " + Table)

            if arcpy.Exists("RevTable"):
                arcpy.Delete_management("RevTable")

        del REVTABLEMAIN,  REVTABLEPOINT, REVTABLELINE, REVTABLEPOLY

    except SystemExit:

        # If the script fails...
        arcpy.AddMessage("Exiting the script")
        tb = sys.exc_info()[2]
        arcpy.AddMessage("Failed at step 3 \n" "Line %i" % tb.tb_lineno)
        arcpy.AddMessage(e.message)

        # Delete the output shapefile and table if created
        # (likely created incorrectly)
        if arcpy.Exists(FinalPointShape):
            arcpy.Delete_management(FinalPointShape)
        if arcpy.Exists(Table):
            arcpy.Delete_management(Table)
        if arcpy.Exists(TempWksp):
            arcpy.Delete_management(TempWksp)

    finally:

        # Delete temporary layers\shapefiles
        arcpy.AddMessage("Deleting temporary shapefiles.")
        if arcpy.Exists("RevLine"):
            arcpy.Delete_management("RevLine")
        if arcpy.Exists("RevPoly"):
            arcpy.Delete_management("RevPoly")
        if arcpy.Exists("Final_pt"):
            arcpy.Delete_management("Final_pt")
        if arcpy.Exists("TempPoint"):
            arcpy.Delete_management("TempPoint")
        if arcpy.Exists(LineShape):
            arcpy.Delete_management(LineShape)
        if arcpy.Exists(PolyShape):
            arcpy.Delete_management(PolyShape)
        if arcpy.Exists(LineShapeSingle):
            arcpy.Delete_management(LineShapeSingle)
        if arcpy.Exists(LineShapeDissolve):
            arcpy.Delete_management(LineShapeDissolve)
        if arcpy.Exists(PolyShapeSingle):
            arcpy.Delete_management(PolyShapeSingle)
        if arcpy.Exists(PolyShapeDissolve):
            arcpy.Delete_management(PolyShapeDissolve)
        if arcpy.Exists(TempFC):
            arcpy.Delete_management(TempFC)
        if arcpy.Exists(TempWksp):
            arcpy.Delete_management(TempWksp)
        if arcpy.Exists(TempDir):
            shutil.rmtree(TempDir)

        if arcpy.GetInstallInfo()['ProductName'] == 'Desktop':
            arcpy.RefreshCatalog(Workspace)


else:
    arcpy.AddError("Please choose new output directory or delete " \
    + "existing files")

