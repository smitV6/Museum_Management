-- CREATE DATABASE

CREATE DATABASE museum_management;
USE museum_management;

-- MUSEUM TABLE

CREATE TABLE Museum (
    museum_id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    location VARCHAR(200),
    contact_number VARCHAR(20)
);

-- GALLERY TABLE

CREATE TABLE Gallery (
    gallery_id INT PRIMARY KEY,
    museum_id INT,
    name VARCHAR(100) NOT NULL,
    floor_number INT,

    FOREIGN KEY (museum_id)
    REFERENCES Museum(museum_id)
);

-- CURATOR TABLE

CREATE TABLE Curator (
    curator_id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    qualification VARCHAR(100),
    phone_number VARCHAR(20)
);

-- DONOR TABLE

CREATE TABLE Donor (
    donor_id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    address VARCHAR(255),
    contact VARCHAR(20)
);

-- RESTORATION DEPARTMENT TABLE

CREATE TABLE Restoration_Department (
    restoration_id INT PRIMARY KEY,
    date_catalog DATE,
    maintenance_cost DECIMAL(10,2),
    description_for_restoration TEXT
);

-- EXHIBITION TABLE

CREATE TABLE Exhibition (
    exhibition_id INT PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    start_date DATE,
    end_date DATE
);

-- ARTIFACTS TABLE

CREATE TABLE Artifacts (
    artifact_id INT PRIMARY KEY,

    name VARCHAR(100) NOT NULL,
    material VARCHAR(100),
    value DECIMAL(12,2),
    origin VARCHAR(100),
    age INT,

    donor_id INT,
    curator_id INT,
    gallery_id INT,
    exhibition_id INT,
    restoration_id INT,

    FOREIGN KEY (donor_id)
    REFERENCES Donor(donor_id),

    FOREIGN KEY (curator_id)
    REFERENCES Curator(curator_id),

    FOREIGN KEY (gallery_id)
    REFERENCES Gallery(gallery_id),

    FOREIGN KEY (exhibition_id)
    REFERENCES Exhibition(exhibition_id),

    FOREIGN KEY (restoration_id)
    REFERENCES Restoration_Department(restoration_id)
);

-- SAMPLE DATA

INSERT INTO Museum
VALUES
(1,'National Museum','Mumbai','9876543210');

INSERT INTO Gallery
VALUES
(101,1,'Ancient Gallery',1),
(102,1,'Modern Gallery',2);

INSERT INTO Curator
VALUES
(1,'Raj Patel','MA History','9876500000');

INSERT INTO Donor
VALUES
(1,'Amit Shah','Mumbai','9988776655');

INSERT INTO Restoration_Department
VALUES
(1,'2025-01-15',25000.00,'Metal restoration');

INSERT INTO Exhibition
VALUES
(1,'Indian Heritage','2025-01-01','2025-12-31');

INSERT INTO Artifacts
VALUES
(
1,
'Ashokan Coin',
'Bronze',
50000.00,
'India',
2200,
1,
1,
101,
1,
1
);

-- VIEW ALL TABLES

SELECT * FROM Museum;
SELECT * FROM Gallery;
SELECT * FROM Curator;
SELECT * FROM Donor;
SELECT * FROM Restoration_Department;
SELECT * FROM Exhibition;
SELECT * FROM Artifacts;

-- ARTIFACTS WITH DONOR DETAILS

SELECT
A.artifact_id,
A.name AS artifact_name,
D.name AS donor_name
FROM Artifacts A
JOIN Donor D
ON A.donor_id = D.donor_id;

-- ARTIFACTS WITH CURATOR DETAILS

SELECT
A.artifact_id,
A.name AS artifact_name,
C.name AS curator_name
FROM Artifacts A
JOIN Curator C
ON A.curator_id = C.curator_id;

-- ARTIFACTS WITH GALLERY DETAILS

SELECT
A.artifact_id,
A.name AS artifact_name,
G.name AS gallery_name
FROM Artifacts A
JOIN Gallery G
ON A.gallery_id = G.gallery_id;

-- ARTIFACTS WITH EXHIBITION DETAILS

SELECT
A.artifact_id,
A.name AS artifact_name,
E.title AS exhibition_title
FROM Artifacts A
JOIN Exhibition E
ON A.exhibition_id = E.exhibition_id;

-- ARTIFACTS UNDER RESTORATION

SELECT
A.artifact_id,
A.name,
R.description_for_restoration,
R.maintenance_cost
FROM Artifacts A
JOIN Restoration_Department R
ON A.restoration_id = R.restoration_id;

-- MUSEUM AND GALLERY DETAILS

SELECT
M.name AS museum_name,
G.name AS gallery_name,
G.floor_number
FROM Museum M
JOIN Gallery G
ON M.museum_id = G.museum_id;
