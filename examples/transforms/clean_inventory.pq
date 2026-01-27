// clean_inventory.pq
// 
// Cleans raw inventory data by:
// - Promoting headers
// - Typing columns
// - Filtering invalid rows (negative quantities)
// - Adding a stock status column
//
// Input: [[InputPath]] - Path to CSV file with columns: SKU, Quantity, LastUpdated
// Output: Table with columns: SKU, Quantity, LastUpdated, Status

let
    // Load input data
    RawData = Csv.Document(
        File.Contents([[InputPath]]),
        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    
    // Promote first row to headers
    PromotedHeaders = Table.PromoteHeaders(RawData, [PromoteAllScalars=true]),
    
    // Set column types
    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {
        {"SKU", type text},
        {"Quantity", Int64.Type},
        {"LastUpdated", type date}
    }),
    
    // Filter out invalid rows (negative quantities)
    ValidRows = Table.SelectRows(TypedColumns, each [Quantity] >= 0),
    
    // Add computed Status column
    WithStatus = Table.AddColumn(ValidRows, "Status", each 
        if [Quantity] = 0 then "Out of Stock"
        else if [Quantity] < 10 then "Low Stock"
        else "In Stock",
        type text
    )
in
    WithStatus
